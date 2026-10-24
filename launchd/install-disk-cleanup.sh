#!/usr/bin/env bash
# Install disk-cleanup.py as a daily LaunchAgent.
# Re-running is idempotent: unloads the old job, copies the script, reloads.
#
# The agent runs with --apply. A manual dry-run is:
#   ~/.local/bin/disk-cleanup.py

set -euo pipefail

SCRIPT_SRC="$(cd "$(dirname "$0")/../bin" && pwd)/disk-cleanup.py"
SCRIPT_DST="$HOME/.local/bin/disk-cleanup.py"
PLIST="$HOME/Library/LaunchAgents/com.dzianisv.disk-cleanup.plist"
LABEL="com.dzianisv.disk-cleanup"
LOG_DIR="$HOME/Library/Logs/disk-cleanup"
INTERVAL=86400

mkdir -p "$HOME/.local/bin" "$LOG_DIR"
cp "$SCRIPT_SRC" "$SCRIPT_DST"
chmod +x "$SCRIPT_DST"

if launchctl list "$LABEL" &>/dev/null; then
    launchctl unload "$PLIST" 2>/dev/null || true
fi

cat > "$PLIST" << EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>${LABEL}</string>
    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>/opt/homebrew/bin:/opt/homebrew/sbin:${HOME}/.local/bin:/usr/bin:/bin:/usr/sbin:/sbin</string>
    </dict>
    <key>ProgramArguments</key>
    <array>
        <string>/usr/bin/python3</string>
        <string>${SCRIPT_DST}</string>
        <string>--apply</string>
    </array>
    <key>StartInterval</key>
    <integer>${INTERVAL}</integer>
    <key>RunAtLoad</key>
    <false/>
    <key>StandardOutPath</key>
    <string>${LOG_DIR}/stdout.log</string>
    <key>StandardErrorPath</key>
    <string>${LOG_DIR}/stderr.log</string>
</dict>
</plist>
EOF

launchctl load "$PLIST"
echo "Installed ${LABEL}. Runs every 24h with --apply."
echo "Dry-run:  $SCRIPT_DST"
echo "Run now:  launchctl start $LABEL"
echo "Logs:     $LOG_DIR/"
echo "Uninstall: launchctl unload $PLIST && rm $PLIST"
