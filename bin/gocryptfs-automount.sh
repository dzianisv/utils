#!/bin/bash

# Define the path to the mount directory
if [ $(uname -s) == "Darwin" ]; then
    MOUNT_DIRECTORY="/Volumes/"
else
    MOUNT_DIRECTORY="/media/$USER/"
fi

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

    # Mount the encrypted folder
    if cat < $password_file | gocryptfs "$folder_path" "$MOUNT_DIRECTORY/$name"; then
        echo "Mounted encrypted folder: $folder_path"
    else
        echo "Failed to mount encrypted folder: $folder_path"
    fi
}

# Function to scan the disk for gocryptfs filesystems and mount them
scan_and_mount() {
    local disk_path="$1"

    # Check if the disk is mounted
    if [ ! -d "$disk_path" ]; then
        echo "Disk not found: $disk_path"
        return 1
    fi

    # Find all gocryptfs filesystems in the root folders of the disk
    local gocryptfs_configs=$(find "$disk_path" -maxdepth 2 -name "gocryptfs.conf")
    for gocryptfs_config in $gocryptfs_configs; do
        local encrypted_folder=$(dirname $gocryptfs_config)
        mount_encrypted_folder "$encrypted_folder"
    done
}


mount | awk '{print $3}' | while read mountpoint; do
    scan_and_mount "$mountpoint"
done
