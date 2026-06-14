#!/usr/bin/env bash
# Installs claude-session-offload as a daily LaunchAgent (runs at 03:00 local time).
# Re-running is idempotent — unloads before replacing.

set -euo pipefail

SCRIPT_SRC="$(cd "$(dirname "$0")/../bin" && pwd)/claude-session-offload.sh"
SCRIPT_DST="$HOME/.local/bin/claude-session-offload.sh"
PLIST="$HOME/Library/LaunchAgents/com.dzianisv.claude-session-offload.plist"
LABEL="com.dzianisv.claude-session-offload"
LOG_DIR="$HOME/Library/Logs/claude-session-offload"

mkdir -p "$HOME/.local/bin" "$LOG_DIR"
cp "$SCRIPT_SRC" "$SCRIPT_DST"
chmod +x "$SCRIPT_DST"

# Unload existing job if present
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
    <key>ProgramArguments</key>
    <array>
        <string>/bin/bash</string>
        <string>${SCRIPT_DST}</string>
    </array>
    <key>StartCalendarInterval</key>
    <dict>
        <key>Hour</key>
        <integer>3</integer>
        <key>Minute</key>
        <integer>0</integer>
    </dict>
    <key>StandardOutPath</key>
    <string>${LOG_DIR}/stdout.log</string>
    <key>StandardErrorPath</key>
    <string>${LOG_DIR}/stderr.log</string>
    <key>RunAtLoad</key>
    <false/>
</dict>
</plist>
EOF

launchctl load "$PLIST"
echo "Installed. Job will run daily at 03:00."
echo "Manual trigger: launchctl start $LABEL"
echo "Logs: $LOG_DIR/"
echo "Uninstall: launchctl unload $PLIST && rm $PLIST $SCRIPT_DST"
