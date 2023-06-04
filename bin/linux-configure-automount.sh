#!/bin/bash
set -euo pipefail

# Install udisks2
if ! command -v udisksctl; then
    apt-get update
    apt-get install -y udisks2
fi

# Create the udev rule
cat > /etc/udev/rules.d/99-usb-automount.rules << EOF
ACTION=="add", KERNEL=="sd[a-z][1-9]", RUN+="/usr/local/bin/automount /dev/%k"
EOF

# Create the automount script
cat > /usr/local/bin/automount << 'EOF'
#!/bin/bash
set -euo pipefail

DEV="$1"
MOUNT_DIRECTORY="/media/$USER/"
CONFIG_DIRECTORY="$HOME/.config/automount"

# Function to mount the encrypted folder
mount_encrypted_folder() {
    local folder_path="$1"
    local name=$(basename $folder_path)
    local password_file="$CONFIG_DIRECTORY/$name"

    # Check if the password file exists
    if [ ! -f "$password_file" ]; then
        echo "Password file does not exist: $password_file"
        return 1
    fi

    local cryptfs_mount_path="$MOUNT_DIRECTORY/$name"
    mkdir -p "$cryptfs_mount_path"

    if [[ ! -d "$cryptfs_mount_path" ]] || [[ ! -z $(ls -A "$cryptfs_mount_path") ]]; then
        echo "$cryptfs_mount_path is not empty 0_o"
        return 1
    fi

    # Mount the encrypted folder
    if cat < $password_file | gocryptfs "$folder_path" "$cryptfs_mount_path"; then
        echo "Mounted encrypted folder: $folder_path"
    else
        echo "Failed to mount encrypted folder: $folder_path"
        return 1
    fi
}

# Function to scan the disk for gocryptfs filesystems and mount them
scan_and_mount() {
    local disk_mount_path="$1"

    # Check if the disk is mounted
    if [ ! -d "$disk_mount_path" ]; then
        echo "Disk not found: $disk_mount_path"
        return 1
    fi

    # Find all gocryptfs filesystems in the root folders of the disk
    local gocryptfs_configs=$(find "$disk_mount_path" -maxdepth 3 -name "gocryptfs.conf")
    for gocryptfs_config in $gocryptfs_configs; do
        local encrypted_folder=$(dirname $gocryptfs_config)
        mount_encrypted_folder "$encrypted_folder"
    done
}
udisk_output=$(udisksctl mount --block-device "$DEV" --no-user-interaction 2>&1)
echo "$udisk_output"
mount_path=$(echo "$udisk_output" | sed -n -e 's/^.* at \(.*\)$/\1/p')
scan_and_mount "$mount_path"
EOF

# Make the automount script executable
chmod a+x /usr/local/bin/automount

# Reload the udev rules
udevadm control --reload-rules

echo "Done!"
