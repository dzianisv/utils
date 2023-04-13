#!/bin/bash

# Path to the directory containing the MP3 files to copy
SOURCE_DIR="$HOME/Resilio Sync/Music"

# Name of the USB flash drive (as shown in the Finder)
DRIVE_NAME="DZIANISMINI"

# Path to the copy-music.sh script
SCRIPT_PATH="/usr/local/bin/copy-music.sh"

# Path to the launchd job
LAUNCHD_PATH="/Library/LaunchDaemons/com.example.copy-music.plist"

# Create the script file
sudo mkdir -p "$(dirname "$SCRIPT_PATH")"
sudo tee "$SCRIPT_PATH" > /dev/null << EOF
#!/bin/bash

# Get the mount point of the drive
DRIVE_MOUNT=\$(diskutil info "$DRIVE_NAME" | grep "Mount Point" | awk '{print \$3}')

# Check if the drive is mounted
if [[ -z "\$DRIVE_MOUNT" ]]; then
    exit
fi

# Copy the MP3 files to the drive
rsync -av --progress "$SOURCE_DIR/" "\$DRIVE_MOUNT/"
EOF

# Make the script executable
sudo chmod +x "$SCRIPT_PATH"

# Create the launchd job file
sudo tee "$LAUNCHD_PATH" > /dev/null << EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple Computer//DTD PLIST 1.0//EN"
 "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.example.copy-music</string>
    <key>ProgramArguments</key>
    <array>
        <string>$SCRIPT_PATH</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>WatchPaths</key>
    <array>
        <string>/Volumes/</string>
    </array>
</dict>
</plist>
EOF

sudo launchctl load "$LAUNCHD_PATH"