#!/bin/sh

#!/bin/bash

# Check if the script is run with root privileges
if [ "$(id -u)" -ne 0 ]; then
  echo "This script must be run as root."
  exit 1
fi

# Prompt user for SSID and password
read -p "Enter the SSID: " SSID
read -sp "Enter the password: " PASSWORD
echo

# Generate a UUID for the connection
UUID=$(uuidgen)

# Create a connection name based on the SSID
CONN_NAME="wifi-${SSID}"

# Create a configuration file in the appropriate directory
CONFIG_FILE="/etc/NetworkManager/system-connections/${CONN_NAME}.nmconnection"

# Write the configuration to the file
cat > "$CONFIG_FILE" << EOF
[connection]
id=${CONN_NAME}
uuid=${UUID}
type=wifi

[wifi]
mode=infrastructure
ssid=${SSID}

[wifi-security]
key-mgmt=wpa-psk
psk=${PASSWORD}

[ipv4]
method=auto

[ipv6]
method=auto
EOF

# Set the permissions for the configuration file
chmod 600 "$CONFIG_FILE"

# Restart NetworkManager to apply the changes
systemctl restart NetworkManager

echo "The configuration file for ${SSID} has been created."


