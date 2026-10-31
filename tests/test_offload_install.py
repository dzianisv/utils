import importlib.util
import os
from pathlib import Path
import plistlib
import subprocess
import sys
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("offload_install", ROOT / "bin/offload-install.py")
installer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)


class InstallerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="offload-install-")
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name) / "home with spaces"
        self.home.mkdir()
        self.script = self.home / "offload % $ test"
        self.script.write_text("#!/bin/bash\n")
        self.calls = []
        self.loaded = False

    def fake_call(self, *args, check=True):
        self.calls.append(args)
        if args[:2] == ("launchctl", "print"):
            path = self.home / "Library/LaunchAgents" / (installer.LABEL + ".plist")
            if args[2].endswith("com.vibetechnologies.workspace-cleanup"):
                wrapper = self.home / ".local/bin/workspace-cleanup-daily.sh"
                return subprocess.CompletedProcess(args, 0 if self.loaded else 1,
                                                   f'program = {wrapper}\n"Hour" => 2\n"Minute" => 0', "")
            return subprocess.CompletedProcess(args, 0 if self.loaded else 1, f"path = {path}", "")
        if args[:2] == ("launchctl", "bootstrap"):
            self.loaded = True
        return subprocess.CompletedProcess(args, 0, "", "")

    def test_launchd_installs_daily_and_reinstall_is_idempotent(self):
        with mock.patch.object(installer, "call", side_effect=self.fake_call):
            installer.install_launchd(self.home, self.script, {"AGENT_ARCHIVE_VOLUME": "/external disk"})
            installer.install_launchd(self.home, self.script, {"AGENT_ARCHIVE_VOLUME": "/external disk"})
        path = self.home / "Library/LaunchAgents" / (installer.LABEL + ".plist")
        with path.open("rb") as file:
            config = plistlib.load(file)
        self.assertEqual(config["StartCalendarInterval"], {"Hour": 2, "Minute": 0})
        self.assertEqual(config["ProgramArguments"], ["/bin/bash", str(self.script), "--execute", "--days", "7"])
        self.assertEqual(config["EnvironmentVariables"]["AGENT_ARCHIVE_VOLUME"], "/external disk")
        self.assertEqual(sum(call[:2] == ("launchctl", "bootstrap") for call in self.calls), 1)

    def test_systemd_installs_daily_persistent_timer_and_quotes_paths(self):
        with mock.patch.object(installer, "call", side_effect=self.fake_call):
            installer.install_systemd(self.home, self.script, {"AGENT_ARCHIVE_VOLUME": "/external % disk"})
            installer.install_systemd(self.home, self.script, {"AGENT_ARCHIVE_VOLUME": "/external % disk"})
        units = self.home / ".config/systemd/user"
        service = (units / "agent-history-offload.service").read_text()
        timer = (units / "agent-history-offload.timer").read_text()
        escaped = str(self.script).replace("%", "%%").replace("$", "$$")
        self.assertIn(f'ExecStart="/bin/bash" "{escaped}" "--execute" "--days" "7"', service)
        self.assertIn('Environment="AGENT_ARCHIVE_VOLUME=/external %% disk"', service)
        self.assertIn("OnCalendar=*-*-* 02:00:00\n", timer)
        self.assertIn("Persistent=true\n", timer)
        self.assertIn(("systemctl", "--user", "enable", "--now", "agent-history-offload.timer"), self.calls)
        self.assertIn(("systemctl", "--user", "is-active", "agent-history-offload.timer"), self.calls)

    def test_conflicting_existing_service_is_preserved(self):
        units = self.home / ".config/systemd/user"
        units.mkdir(parents=True)
        existing = units / "agent-history-offload.service"
        existing.write_text("user-managed\n")
        with mock.patch.object(installer, "call", side_effect=self.fake_call):
            with self.assertRaisesRegex(RuntimeError, "refusing to overwrite"):
                installer.install_systemd(self.home, self.script, {})
        self.assertEqual(existing.read_text(), "user-managed\n")
        self.assertFalse((units / "agent-history-offload.timer").exists())

    def test_launchd_bootstrap_failure_removes_new_plist(self):
        def failed(*args, check=True):
            if args[:2] == ("launchctl", "bootstrap"):
                raise RuntimeError("bootstrap failed")
            return self.fake_call(*args, check=check)
        with mock.patch.object(installer, "call", side_effect=failed):
            with self.assertRaisesRegex(RuntimeError, "bootstrap failed"):
                installer.install_launchd(self.home, self.script, {})
        self.assertFalse((self.home / "Library/LaunchAgents" / (installer.LABEL + ".plist")).exists())

    def test_systemd_failure_rolls_back_new_units(self):
        def failed(*args, check=True):
            if args[:4] == ("systemctl", "--user", "enable", "--now"):
                raise RuntimeError("enable failed")
            return self.fake_call(*args, check=check)
        with mock.patch.object(installer, "call", side_effect=failed):
            with self.assertRaisesRegex(RuntimeError, "enable failed"):
                installer.install_systemd(self.home, self.script, {})
        units = self.home / ".config/systemd/user"
        self.assertFalse((units / "agent-history-offload.service").exists())
        self.assertFalse((units / "agent-history-offload.timer").exists())

    def test_linux_entrypoint_routes_to_systemd(self):
        env = {"HOME": str(self.home)}
        with mock.patch.dict(os.environ, env, clear=True), \
             mock.patch.object(installer.platform, "system", return_value="Linux"), \
             mock.patch.object(installer, "call", side_effect=self.fake_call), \
             mock.patch.object(sys, "argv", ["offload-install.py", str(self.script)]):
            self.assertEqual(installer.main(), 0)
        self.assertTrue((self.home / ".config/systemd/user/agent-history-offload.timer").is_file())

    def test_existing_workspace_job_is_reused(self):
        script = self.home / "workspace/utils/bin/offload"
        script.parent.mkdir(parents=True)
        script.write_text("#!/bin/bash\n")
        wrapper = self.home / ".local/bin/workspace-cleanup-daily.sh"
        wrapper.parent.mkdir(parents=True)
        wrapper.write_text('HISTORY_SCRIPT="$HOME/workspace/utils/bin/offload"\n'
                           '"$HISTORY_SCRIPT" --execute --pi-only --days 7\n'
                           '"$HISTORY_SCRIPT" --execute --opencode-only --days 7\n'
                           '"$HISTORY_SCRIPT" --execute --hermes-only --days 7\n')
        agents = self.home / "Library/LaunchAgents"
        agents.mkdir(parents=True)
        with (agents / "com.vibetechnologies.workspace-cleanup.plist").open("wb") as file:
            plistlib.dump({"ProgramArguments": [str(wrapper)],
                           "StartCalendarInterval": {"Hour": 2, "Minute": 0}}, file)
        self.loaded = True
        with mock.patch.object(installer, "call", side_effect=self.fake_call):
            installer.install_launchd(self.home, script.resolve(), {})
        self.assertFalse((agents / (installer.LABEL + ".plist")).exists())
        self.assertFalse(any(call[:2] == ("launchctl", "bootstrap") for call in self.calls))

    def test_install_rejects_other_options_before_mount_check(self):
        result = subprocess.run([str(ROOT / "bin/offload"), "--install", "--execute"],
                                capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("--install cannot be combined", result.stderr)

    @unittest.skipUnless(sys.platform == "darwin", "launchctl entrypoint requires macOS")
    def test_install_entrypoint_with_fake_launchctl(self):
        fakebin = self.home / "fakebin"
        fakebin.mkdir()
        launchctl = fakebin / "launchctl"
        launchctl.write_text('#!/bin/bash\ncase "$1" in\n'
                             'print) test -f "$HOME/loaded" && printf "path = %s\\n" "$HOME/Library/LaunchAgents/com.user.agent-history-offload.plist";;\n'
                             'bootstrap) touch "$HOME/loaded";;\n'
                             '*) exit 0;;\nesac\n')
        launchctl.chmod(0o755)
        env = dict(os.environ, HOME=str(self.home), PATH=str(fakebin) + os.pathsep + os.environ["PATH"])
        for key in installer.ENV_KEYS:
            env.pop(key, None)
        result = subprocess.run([str(ROOT / "bin/offload"), "--install"], env=env, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        path = self.home / "Library/LaunchAgents" / (installer.LABEL + ".plist")
        with path.open("rb") as file:
            config = plistlib.load(file)
        self.assertEqual(config["ProgramArguments"], ["/bin/bash", str((ROOT / "bin/offload").resolve()), "--execute", "--days", "7"])


if __name__ == "__main__":
    unittest.main()
