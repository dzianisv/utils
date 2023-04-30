#!/bin/bash

# Check if running as root
if [ "$(id -u)" -ne 0 ]; then
    echo "Please run this script as root."
    exit 1
fi

UDEV_RULES_FILE="/etc/udev/rules.d/99-automount_gocryptfs.rules"
AUTOMOUNT_SCRIPT="/usr/local/bin/automount_gocryptfs.sh"

# Create automount script
cat > "$AUTOMOUNT_SCRIPT" << EOL
#!/bin/bash

# Variables
DEVNAME=\$1

# Wait for the mount point to become available
MOUNT_PARENT=""
TRIES=0
while [[ -z "\$MOUNT_PARENT" && \$TRIES -lt 30 ]]; do
    sleep 1
    MOUNT_PARENT=\$(findmnt -n -o TARGET "\$DEVNAME")
    TRIES=\$((TRIES + 1))
done

if [[ -z "\$MOUNT_PARENT" ]]; then
    echo "Mount point not found."
    exit 1
fi

ENCRYPTED_DIR="\${MOUNT_PARENT}/d"

# Check if encrypted directory exists
if [ -d "\$ENCRYPTED_DIR" ]; then
    # Get the owner of the encrypted directory
    USER=\$(stat -c '%U' "\$ENCRYPTED_DIR")

    # Get the disk label
    DISK_LABEL=\$(lsblk -no LABEL "\$DEVNAME")
    
    MOUNT_POINT="/home/\$USER/.mnt/\$DISK_LABEL"
    mkdir -p "\$MOUNT_POINT"
    CONFIG_DIR="/home/\$USER/.config/automount"
    PASSWORD_FILE="\$CONFIG_DIR/\${DISK_LABEL}"
    
    # Check if password file exists
    if [ -f "\$PASSWORD_FILE" ]; then
        # Create mount point if it doesn't exist
        mkdir -p "\$MOUNT_POINT"
        # Change ownership of the mount point
        chown -R \$USER:\$USER "\$MOUNT_POINT"

        # Get password and mount encrypted directory
        PASSWORD=\$(cat "\$PASSWORD_FILE")
        echo "\$PASSWORD" | sudo -u \$USER gocryptfs "\$ENCRYPTED_DIR" "\$MOUNT_POINT"
    else
        echo "Password file not found."
        exit 1
    fi
else
    echo "Encrypted directory not found."
    exit 1
fi
EOL

# Make the automount script executable
chmod +x "$AUTOMOUNT_SCRIPT"

# Create udev rule
cat > "$UDEV_RULES_FILE" << EOL
ACTION=="add", KERNEL=="sd[a-z][0-9]", RUN+="$AUTOMOUNT_SCRIPT '%k'"
EOL

# Reload udev rules
udevadm control --reload-rules
udevadm trigger

echo "Installation complete."
