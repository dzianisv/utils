#!/bin/bash

# Define the name of the service
SERVICE_NAME="usb-automount.service"

# Define the path to the service file
SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}"

# Define the content of the service file
SERVICE_CONTENT="[Unit]
Description=Automount Mount Service

[Service]
ExecStart=/bin/bash -c 'mount -o uid=\$(id -u rslsync),gid=\$(id -g rslsync) /dev/disk/by-label/External5TB /data/'
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target"

# Write the service file
echo "${SERVICE_CONTENT}" | sudo tee ${SERVICE_FILE} > /dev/null

# Reload the systemd configuration
systemctl daemon-reload

# Enable the service to start on boot
systemctl enable ${SERVICE_NAME}

# Start the service
systemctl start ${SERVICE_NAME}

# Check the status of the service
systemctl status ${SERVICE_NAME}
