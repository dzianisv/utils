#!/bin/bash

# Check if the script is run as root
if [[ $EUID -ne 0 ]]; then
   echo "This script must be run as root"
   exit 1
fi

# Check if udisksctl is installed
if ! command -v udisksctl &> /dev/null; then
    echo "udisksctl is not installed. Installing udisks2 now..."
    apt update && apt install -y udisks2
    if [[ $? -ne 0 ]]; then
        echo "Failed to install udisks2. Please check your package manager and try again."
        exit 1
    fi
fi

# 1. Write the shell script into /usr/local/bin/udisk-automount.sh
cat > /usr/local/bin/udisk-automount.sh << 'EOL'
#!/bin/bash
lsblk -o PATH,MOUNTPOINT | while read -r device_path mountpoint; do
    # Check if the mountpoint is empty
    if [ -z "$mountpoint" ]; then
        # Mount the device using udisksctl
        udisksctl mount -b "$device_path"
    fi
done
EOL

# Make the script executable
chmod +x /usr/local/bin/udisk-automount.sh

# 2. Install systemd service and timer
cat > /etc/systemd/system/udisk-automount.service << 'EOL'
[Unit]
Description=Mount unmounted block devices using udisksctl

[Service]
Type=oneshot
ExecStart=/usr/local/bin/udisk-automount.sh
EOL

cat > /etc/systemd/system/udisk-automount.timer << 'EOL'
[Unit]
Description=Run udisks automount every 30 seconds

[Timer]
OnBootSec=10
OnUnitActiveSec=30

[Install]
WantedBy=timers.target
EOL

# 3. Enable and start the timer
systemctl daemon-reload
systemctl enable udisk-automount.timer
systemctl start udisk-automount.timer

echo "Installation complete!"
