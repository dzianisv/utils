#!/bin/bash

# 1. Install the script from GitHub to /usr/local/bin/transfer-dcim
curl -o /usr/local/bin/transfer-dcim "https://raw.githubusercontent.com/dzianisv/utils/master/bin/transfer-dcim"
chmod +x /usr/local/bin/transfer-dcim

# Create the systemd service file
cat <<EOL > /etc/systemd/system/transfer-dcim.service
[Unit]
Description=Transfer DCIM Service

[Service]
Type=oneshot
ExecStart=/usr/local/bin/transfer-dcim
EOL

# Create the systemd timer file
cat <<EOL > /etc/systemd/system/transfer-dcim.timer
[Unit]
Description=Run transfer-dcim every minute

[Timer]
OnBootSec=1min
OnUnitActiveSec=1min
Unit=transfer-dcim.service

[Install]
WantedBy=multi-user.target
EOL

# Reload systemd, enable and start the timer
systemctl daemon-reload
systemctl enable transfer-dcim.timer
systemctl start transfer-dcim.timer
