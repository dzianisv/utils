#!/bin/bash

# Check if running as root
if [[ $EUID -ne 0 ]]; then
    echo "Please run this script as root or with sudo."
    exit 1
fi

# Get the public IPv4 address
PUBLIC_IP=$(curl -s https://api.ipify.org)

# Perform reverse DNS lookup
DOMAIN_NAME=$(dig +short -x "$PUBLIC_IP")

if [ -z "$DOMAIN_NAME" ]; then
    echo "No domain name found for the public IP address. Please set up a reverse DNS record for your IP address and try again."
    exit 1
fi

# Update package lists
apt-get update

# Install Certbot
apt-get install -y certbot

# Obtain SSL certificate from Let's Encrypt
certbot certonly --standalone --preferred-challenges http --agree-tos --email youremail@example.com -d "$DOMAIN_NAME"
