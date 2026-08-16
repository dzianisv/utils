#!/usr/bin/env bash
# Installs paperclip-run-logs-prune as an hourly LaunchAgent.
# Re-running is idempotent — unloads before replacing.
#
# AGE-312 stage-3: the original daily-at-04:00 cadence let real ENOSPC recur
# within ~13h of a fresh cleanup (fleet-wide npm/pnpm/worktree churn refills
# the disk far faster than once a day). Hourly + 1-day retention keeps the
# host from ever getting more than ~1h of churn away from headroom.

set -euo pipefail

SCRIPT_SRC="$(cd "$(dirname "$0")/../bin" && pwd)/paperclip-run-logs-prune.sh"
SCRIPT_DST="$HOME/.local/bin/paperclip-run-logs-prune.sh"
PLIST="$HOME/Library/LaunchAgents/com.dzianisv.paperclip-run-logs-prune.plist"
LABEL="com.dzianisv.paperclip-run-logs-prune"
LOG_DIR="$HOME/Library/Logs/paperclip-run-logs-prune"

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
    <key>ProgramArguments</key>
    <array>
        <string>/bin/bash</string>
        <string>${SCRIPT_DST}</string>
    </array>
    <key>StartInterval</key>
    <integer>3600</integer>
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
echo "Installed. Job will run hourly."
echo "Manual trigger: launchctl start $LABEL"
echo "Logs: $LOG_DIR/"
echo "Uninstall: launchctl unload $PLIST && rm $PLIST $SCRIPT_DST"
