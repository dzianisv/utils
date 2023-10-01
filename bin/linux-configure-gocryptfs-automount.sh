#!/bin/bash

# Create the systemd service file
cat <<EOL | tee /etc/systemd/system/gocryptfs-automount.service
[Unit]
Description=gocryptfs automount service

[Service]
ExecStart=/usr/local/bin/gocryptfs-automount.sh
Restart=on-failure

[Install]
WantedBy=multi-user.target
EOL

install -m 0755 gocryptfs-automount.sh /usr/local/bin/gocryptfs-automount.sh

# Reload the systemd daemon to recognize the new service
systemctl daemon-reload

# Enable the service to start on boot
systemctl enable gocryptfs-automount.service

# Start the service immediately
systemctl start gocryptfs-automount.service
