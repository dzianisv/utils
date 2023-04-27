#!/bin/bash

# Check if running as root
if [[ $EUID -ne 0 ]]; then
    echo "Please run this script as root or with sudo."
    exit 1
fi

# Check if PROXY_USER and PROXY_PASSWORD are set
if [[ -z "$PROXY_USER" || -z "$PROXY_PASSWORD" ]]; then
    echo "Please set the environment variables PROXY_USER and PROXY_PASSWORD before running this script."
    exit 1
fi

# Update package lists
apt-get update

# Install Squid, Nginx, and Apache2-utils
apt-get install -y squid nginx apache2-utils

# Configure Squid
cat > /etc/squid/squid.conf << EOL
# Define authentication method and password file
auth_param basic program /usr/lib/squid/basic_ncsa_auth /etc/squid/passwords
auth_param basic children 5
auth_param basic realm Squid proxy-caching web server
auth_param basic credentialsttl 2 hours
auth_param basic casesensitive off

# Define access control list (ACL) for authenticated users
acl authenticated_users proxy_auth REQUIRED

# Allow access for authenticated users
http_access allow authenticated_users

# Deny access to all other requests
http_access deny all

# Configure the proxy port
http_port 3128
EOL

# Create password file with user and password from environment variables
htpasswd -c -b /etc/squid/passwords "$PROXY_USER" "$PROXY_PASSWORD"

HOSTNAME=$(ip addr show eth0 | grep -w inet | awk '{print $2}' | cut -f1 -d/)

# Create self-signed SSL certificate
mkdir -p /etc/nginx/ssl
openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
  -subj "/C=US/ST=CA/L=San Francisco/O=Google/CN=${HOSTNAME}" \
  -keyout /etc/nginx/ssl/nginx.key -out /etc/nginx/ssl/nginx.crt

# Configure Nginx as forward-proxy with SSL termination
cat > /etc/nginx/sites-available/squid_proxy << EOL
server {
    listen 80;
    server_name _;
    return 301 https://\$host\$request_uri;
}

server {
    listen 443 ssl;
    server_name _;

    ssl_certificate /etc/nginx/ssl/nginx.crt;
    ssl_certificate_key /etc/nginx/ssl/nginx.key;

    location / {
        proxy_pass http://127.0.0.1:3128;
        proxy_set_header Host \$http_host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_http_version 1.1;
        proxy_set_header Connection "";
        auth_basic "Restricted";
        auth_basic_user_file /etc/squid/passwords;
    }
}
EOL

# Enable Nginx configuration and remove default
rm /etc/nginx/sites-enabled/default
ln -s /etc/nginx/sites-available/squid_proxy /etc/nginx/sites-enabled/squid_proxy

# Restart Squid and Nginx services
systemctl restart squid
systemctl restart nginx
