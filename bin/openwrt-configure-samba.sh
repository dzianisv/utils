#!/bin/sh

# Check if samba4-server is already installed
if opkg list-installed | grep -q "^samba4-server"; then
  echo "Samba4-server is already installed."
else
  # Install samba4
  echo "Installing Samba4..."
  opkg update
  opkg install samba4-server
fi

# Install useradd if not already installed
if ! command -v useradd &> /dev/null; then
  opkg update
  opkg install shadow-useradd
fi

# Create shared folder
echo "Creating shared folder..."
mkdir -p /mnt/

# Ask for user and password
echo "Please enter the username for the Samba user:"
read username
echo "Please enter the password for the Samba user:"
read -s password

# Add user to system and samba
echo "Adding user and setting up permissions..."
useradd $username
echo -e "$password\n$password" | smbpasswd -a $username -s

# Create the Samba directory if it doesn't exist
mkdir -p /etc/samba

# Configure Samba
echo "Configuring Samba..."
cat << EOF > /etc/samba/smb.conf
[global]
   workgroup = WORKGROUP
   server string = Samba Server %v
   netbios name = openwrt
   security = user
   map to guest = Bad User
   log file = /var/log/samba.%m
   max log size = 50

[openwrt]
   path = /mnt/
   valid users = $username
   read only = no
EOF

# Start Samba
samba_service=$(ls /etc/init.d/ | grep samba)
if [ -n "$samba_service" ]; then
  echo "Starting Samba..."
  /etc/init.d/$samba_service start

  # Enable Samba at boot
  echo "Enabling Samba to start at boot..."
  /etc/init.d/$samba_service enable
else
  echo "Could not find Samba service in /etc/init.d"
fi

echo "Samba has been configured and started."


