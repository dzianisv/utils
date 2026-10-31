#!/usr/bin/env python3
"""Install offload as a daily, per-user launchd agent or systemd timer."""
import os
from pathlib import Path
import platform
import plistlib
import subprocess
import sys


LABEL = "com.user.agent-history-offload"
UNIT = "agent-history-offload"
PATH_VALUE = "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
ENV_KEYS = ("AGENT_ARCHIVE_VOLUME", "AGENT_ARCHIVE_ROOT", "PI_SESSIONS",
            "HERMES_HOME", "HERMES_BIN", "OPENCODE_DB")


def call(*args, check=True):
    result = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if check and result.returncode:
        raise RuntimeError(f"{' '.join(args)} failed: {result.stderr.strip() or result.stdout.strip()}")
    return result


def create_or_validate(path, data):
    """Do not replace user-owned or modified service definitions."""
    if path.exists():
        if path.read_bytes() != data:
            raise RuntimeError(f"existing service differs; refusing to overwrite: {path}")
        return False
    try:
        with path.open("xb") as file:
            file.write(data)
    except FileExistsError:
        raise RuntimeError(f"service appeared during installation: {path}")
    return True


def existing_workspace_job(home, script, domain):
    """Recognize the existing, loaded workspace job without changing it."""
    plist = home / "Library/LaunchAgents/com.vibetechnologies.workspace-cleanup.plist"
    wrapper = home / ".local/bin/workspace-cleanup-daily.sh"
    if not plist.is_file() or not wrapper.is_file():
        return False
    if script != (home / "workspace/utils/bin/offload").resolve():
        return False
    try:
        with plist.open("rb") as file:
            config = plistlib.load(file)
        body = wrapper.read_text()
    except (OSError, ValueError, plistlib.InvalidFileException):
        return False
    calendar = config.get("StartCalendarInterval")
    if (config.get("ProgramArguments") != [str(wrapper)] or
            calendar != {"Hour": 2, "Minute": 0} or
            'HISTORY_SCRIPT="$HOME/workspace/utils/bin/offload"' not in body or
            '--execute --opencode-only --days 7' not in body or
            '--execute --pi-only --days 7' not in body or
            '--execute --hermes-only --days 7' not in body):
        return False
    loaded = call("launchctl", "print", f"{domain}/com.vibetechnologies.workspace-cleanup", check=False)
    return (loaded.returncode == 0 and f"program = {wrapper}" in loaded.stdout and
            '"Hour" => 2' in loaded.stdout and '"Minute" => 0' in loaded.stdout)


def install_launchd(home, script, env):
    domain = f"gui/{os.getuid()}"
    if existing_workspace_job(home, script, domain):
        print("Already installed: com.vibetechnologies.workspace-cleanup runs daily at 02:00 (Pi and OpenCode).")
        print("Existing schedule retained; no duplicate agent created.")
        return
    agent_dir = home / "Library/LaunchAgents"
    log_dir = home / "Library/Logs/agent-history-offload"
    agent_dir.mkdir(parents=True, exist_ok=True)
    log_dir.mkdir(parents=True, exist_ok=True)
    path = agent_dir / f"{LABEL}.plist"
    variables = {"HOME": str(home), "PATH": PATH_VALUE}
    variables.update({k: env[k] for k in ENV_KEYS if k in env})
    data = plistlib.dumps({"Label": LABEL, "ProgramArguments": ["/bin/bash", str(script), "--execute", "--days", "7"],
                           "StartCalendarInterval": {"Hour": 2, "Minute": 0}, "RunAtLoad": False,
                           "EnvironmentVariables": variables,
                           "StandardOutPath": str(log_dir / "stdout.log"),
                           "StandardErrorPath": str(log_dir / "stderr.log")}, sort_keys=True)
    existing = call("launchctl", "print", f"{domain}/{LABEL}", check=False)
    loaded = existing.returncode == 0
    if loaded and (not path.is_file() or f"path = {path}" not in existing.stdout):
        raise RuntimeError(f"{LABEL} is loaded from an unknown path; refusing to change it")
    created = create_or_validate(path, data)
    if loaded:
        print(f"Already installed: {path}; daily at 02:00.")
        return
    try:
        call("launchctl", "bootstrap", domain, str(path))
        call("launchctl", "print", f"{domain}/{LABEL}")
    except (OSError, RuntimeError):
        if created:
            call("launchctl", "bootout", f"{domain}/{LABEL}", check=False)
            path.unlink(missing_ok=True)
        raise
    print(f"Installed and loaded: {path}; daily at 02:00.")
    print(f"Command: /bin/bash {script} --execute --days 7")


def systemd_quote(value, command=False):
    # systemd expands percent specifiers even inside quoted arguments.
    if "\n" in value or "\r" in value or "\0" in value:
        raise RuntimeError("newlines and NULs are not supported in service paths or environment")
    value = value.replace("%", "%%")
    if command:
        value = value.replace("$", "$$")
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def install_systemd(home, script, env):
    config_home = Path(env.get("XDG_CONFIG_HOME") or home / ".config")
    if not config_home.is_absolute():
        raise RuntimeError("XDG_CONFIG_HOME must be an absolute path")
    units = config_home / "systemd/user"
    units.mkdir(parents=True, exist_ok=True)
    service, timer = units / f"{UNIT}.service", units / f"{UNIT}.timer"
    variables = {"HOME": str(home), "PATH": PATH_VALUE}
    variables.update({k: env[k] for k in ENV_KEYS if k in env})
    environment = "".join(f"Environment={systemd_quote(k + '=' + v)}\n" for k, v in variables.items())
    command = " ".join(systemd_quote(x, command=True) for x in ("/bin/bash", str(script), "--execute", "--days", "7"))
    service_data = ("[Unit]\nDescription=Offload cold agent sessions\n\n[Service]\nType=oneshot\n" +
                    environment + f"ExecStart={command}\n").encode()
    timer_data = (f"[Unit]\nDescription=Daily agent session offload\n\n[Timer]\nOnCalendar=*-*-* 02:00:00\n"
                  f"Persistent=true\nUnit={UNIT}.service\n\n[Install]\nWantedBy=timers.target\n").encode()
    created = []
    try:
        for path, data in ((service, service_data), (timer, timer_data)):
            if create_or_validate(path, data):
                created.append(path)
        call("systemctl", "--user", "daemon-reload")
        call("systemctl", "--user", "enable", "--now", timer.name)
        call("systemctl", "--user", "is-enabled", timer.name)
        call("systemctl", "--user", "is-active", timer.name)
    except (OSError, RuntimeError):
        if timer in created:
            call("systemctl", "--user", "disable", "--now", timer.name, check=False)
        for path in created:
            path.unlink(missing_ok=True)
        if created:
            call("systemctl", "--user", "daemon-reload", check=False)
        raise
    print(f"Installed and enabled: {timer}; daily at 02:00 (persistent).")
    print(f"Command: /bin/bash {script} --execute --days 7")


def main():
    if len(sys.argv) != 2:
        print("usage: offload-install.py <offload-script>", file=sys.stderr)
        return 2
    home = Path.home()
    script = Path(sys.argv[1]).resolve()
    if not script.is_file():
        print(f"error: offload script not found: {script}", file=sys.stderr)
        return 1
    try:
        system = platform.system()
        if system == "Darwin":
            install_launchd(home, script, os.environ)
        elif system == "Linux":
            install_systemd(home, script, os.environ)
        else:
            raise RuntimeError(f"unsupported operating system: {system}")
    except (OSError, RuntimeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
