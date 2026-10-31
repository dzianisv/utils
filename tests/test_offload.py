import os
from pathlib import Path
import subprocess
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "bin" / "offload"


class OffloadSafetyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="offload-test-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.env = os.environ.copy()
        self.env.update(TMPDIR=str(self.root), USER="offload-test", HOME=str(self.root),
                        AGENT_ARCHIVE_VOLUME=str(self.root / "not-mounted"))

    def run_offload(self):
        return subprocess.run([str(SCRIPT), "--execute", "--pi-only"], env=self.env,
                              capture_output=True, text=True)

    def test_missing_mount_fails_without_creating_archive(self):
        result = self.run_offload()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Archive volume is not mounted", result.stderr)
        self.assertFalse((self.root / "not-mounted").exists())
        self.assertFalse((self.root / "agent-history-offload-offload-test.lock").exists())

    def test_active_lock_is_not_removed_by_rejected_run(self):
        lock = self.root / "agent-history-offload-offload-test.lock"
        lock.mkdir()
        (lock / "pid").write_text(str(os.getpid()))
        result = self.run_offload()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("another offload run is active", result.stderr)
        self.assertEqual((lock / "pid").read_text(), str(os.getpid()))

    def test_hermes_prune_fails_before_any_mutation(self):
        result = subprocess.run([str(SCRIPT), "--execute", "--hermes-only", "--prune-hermes"],
                                env=self.env, capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("export coverage", result.stderr)
        self.assertEqual(list(self.root.iterdir()), [])

    def test_linux_mountpoint_is_accepted(self):
        fakebin = self.root / "bin"
        fakebin.mkdir()
        mountpoint = fakebin / "mountpoint"
        mountpoint.write_text('#!/bin/bash\n[[ "$1" == "-q" && "$2" == "--" && "$3" == "$AGENT_ARCHIVE_VOLUME" ]]\n')
        mountpoint.chmod(0o755)
        volume = self.root / "mounted"
        volume.mkdir()
        self.env.update(PATH=str(fakebin) + os.pathsep + self.env["PATH"],
                        AGENT_ARCHIVE_VOLUME=str(volume), PI_SESSIONS=str(self.root / "no-sessions"))
        result = self.run_offload()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("failed=0", result.stdout)


if __name__ == "__main__":
    unittest.main()
