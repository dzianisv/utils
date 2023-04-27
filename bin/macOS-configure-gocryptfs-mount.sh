#!/bin/bash

# Variables
VOLUME_LABEL=External5TB
VOLUME_PATH="/Volumes/$VOLUME_LABEL"
MOUNT_POINT="$HOME/.mnt/d"
SCRIPT_PATH="/usr/local/bin/mount_gocryptfs.sh"
PLIST_PATH="$HOME/Library/LaunchAgents/com.user.mount_gocryptfs.plist"

# Create mount_gocryptfs.sh script
cat << EOF > "$SCRIPT_PATH"
#!/bin/bash
set -euo pipefail

# Get the password from the keychain
# PASSWORD=\$(security find-generic-password -a "\$USER" -s "External5TB" -w)
PASSWORD=$(< ~/.config/External5TB )
# Mount the gocryptfs volume
gocryptfs -passfile=<(echo "\$PASSWORD") "$VOLUME_PATH/d" "$MOUNT_POINT"
EOF

# Make the script executable
chmod +x "$SCRIPT_PATH"

# Create the launchd plist file
cat << EOF > "$PLIST_PATH"
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.user.mount_gocryptfs</string>
    <key>ProgramArguments</key>
    <array>
        <string>/bin/bash</string>
        <string>$SCRIPT_PATH</string>
    </array>
    <key>RunAtLoad</key>
    <false/>
    <key>KeepAlive</key>
    <false/>
    <key>StartOnMount</key>
    <true/>
</dict>
</plist>
EOF


# Load the launchd daemon
launchctl load "$PLIST_PATH"

echo "Installation complete. The launchd daemon has been loaded."
