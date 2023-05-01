#!/bin/bash

# Set the paths and filenames
SCRIPT_NAME="automount.sh"
SCRIPT_PATH="/usr/local/bin/$SCRIPT_NAME"
PLIST_NAME="com.dzianisv.automount.plist"
PLIST_PATH="$HOME/Library/LaunchAgents/$PLIST_NAME"

# Create the mount directory
MOUNT_DIRECTORY="$HOME/.mnt"
install -d "$MOUNT_DIRECTORY"

# Create the configuration directory
CONFIG_DIRECTORY="$HOME/.config/automount"
install -d 0600 "$CONFIG_DIRECTORY"

# Create the automount.sh script file
cat << EOF > "$SCRIPT_PATH"
#!/bin/bash

# Define the path to the mount directory
MOUNT_DIRECTORY="\$HOME/.mnt"

# Function to mount the encrypted folder
mount_encrypted_folder() {
    local folder_path="\$1"
    local name=\$(basename \$folder_path)
    local password_file="$CONFIG_DIRECTORY/\$name"

    # Check if the password file exists
    if [ ! -f "\$password_file" ]; then
        echo "Password file does not exist: \$password_file"
        return 1
    fi

    # Mount the encrypted folder
    if cat < \$password_file | gocryptfs "\$folder_path" "\$MOUNT_DIRECTORY/\$name"; then
        echo "Mounted encrypted folder: \$folder_path"
    else
        echo "Failed to mount encrypted folder: \$folder_path"
    fi
}

# Function to scan the disk for gocryptfs filesystems and mount them
scan_and_mount() {
    local disk_path="\$1"

    # Check if the disk is mounted
    if [ ! -d "\$disk_path" ]; then
        echo "Disk not found: \$disk_path"
        return 1
    fi

    # Find all gocryptfs filesystems in the root folders of the disk
    local gocryptfs_configs=\$(find "\$disk_path" -maxdepth 2 -name "gocryptfs.conf")
    for gocryptfs_config in \$gocryptfs_configs; do
        local encrypted_folder=\$(dirname \$gocryptfs_config)
        mount_encrypted_folder "\$encrypted_folder"
    done
}

# Get the disk path and label from the launchd environment variables
disk_path="\$1"

if [ -z "\$disk_path" ]; then
    echo "No disk path provided"
    exit 1
fi

scan_and_mount "\$disk_path"
EOF

# Set the permissions for the script file
chmod +x "$SCRIPT_PATH"

# Create the property list file
cat << EOF > "$PLIST_PATH"
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//PLIST_NAME">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>$PLIST_NAME</string>
    <key>ProgramArguments</key>
    <array>
        <string>$SCRIPT_PATH</string>
        <string>%v</string>
    </array>
    <key>WatchPaths</key>
    <array>
        <string>/Volumes</string>
    </array>
</dict>
</plist>
EOF

# Load the launchd daemon
launchctl load "$PLIST_PATH"

echo "Installation completed successfully."