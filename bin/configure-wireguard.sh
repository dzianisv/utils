#!/bin/bash

# Check if the script is run as root
if [ "$(id -u)" != "0" ]; then
    echo "This script must be run as root"
    exit 1
fi

# Install WireGuard
apt update
apt install -y wireguard

# Server configuration
SERVER_PORT=51820
SERVER_PUBLIC_IP=$(curl -s ifconfig.me)
SERVER_CONFIG="/etc/wireguard/wg0.conf"
umask 077

# Generate server private and public keys
SERVER_PRIVATE_KEY=$(wg genkey)
SERVER_PUBLIC_KEY=$(echo "${SERVER_PRIVATE_KEY}" | wg pubkey)

# Create server configuration
cat << EOF > $SERVER_CONFIG
[Interface]
PrivateKey = $SERVER_PRIVATE_KEY
Address = 10.0.0.1/24
ListenPort = $SERVER_PORT
PostUp = iptables -A FORWARD -i %i -j ACCEPT; iptables -t nat -A POSTROUTING -o eth0 -j MASQUERADE
PostDown = iptables -D FORWARD -i %i -j ACCEPT; iptables -t nat -D POSTROUTING -o eth0 -j MASQUERADE

EOF

# Generate client configurations
read -p "Enter the number of clients: " N
for i in $(seq 1 $N); do
    CLIENT_CONFIG="wg-${SERVER_PUBLIC_IP}-client${i}.conf"
    CLIENT_PRIVATE_KEY=$(wg genkey)
    CLIENT_PUBLIC_KEY=$(echo "${CLIENT_PRIVATE_KEY}" | wg pubkey)
    # Add client peer to server configuration
    cat << EOF >> $SERVER_CONFIG
[Peer]
PublicKey = $CLIENT_PUBLIC_KEY
AllowedIPs = 0.0.0.0/0, ::/0

EOF

    # Create client configuration
    cat << EOF > $CLIENT_CONFIG
[Interface]
PrivateKey = $CLIENT_PRIVATE_KEY
Address = 10.0.0.$(($i+1))/24
DNS = 1.1.1.1

[Peer]
PublicKey = $SERVER_PUBLIC_KEY
Endpoint = $SERVER_PUBLIC_IP:$SERVER_PORT
AllowedIPs = 0.0.0.0/0, ::/0
PersistentKeepalive = 25

EOF
done

# Enable and start the WireGuard server
systemctl enable wg-quick@wg0
systemctl start wg-quick@wg0
echo "WireGuard server is up and running"
