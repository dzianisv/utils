#!/bin/bash

set -euo pipefail

apt-get update
apt-get install -y pptpd

# Configure PPTP server
cat > /etc/pptpd.conf << EOL
option /etc/ppp/pptpd-options
logwtmp
localip 192.168.240.1
remoteip 192.168.240.100-200
EOL


# Configure PPP options
cat > /etc/ppp/pptpd-options << EOL
name pptpd
refuse-pap
refuse-chap
refuse-mschap
refuse-mschap-v2
require-mppe-128
ms-dns 8.8.8.8
ms-dns 8.8.4.4
proxyarp
nodefaultroute
lock
nobsdcomp
novj
novjccomp
nologfd
EOL


# Configure PPTP server credentials
read -p "Enter the PPTP username: " USERNAME
read -s -p "Enter the PPTP password: " PASSWORD
echo ""
echo '${USERNAME} pptpd ${PASSWORD} *' >> /etc/ppp/chap-secrets

# Enable IP forwarding
sed -i 's/#net.ipv4.ip_forward=1/net.ipv4.ip_forward=1/g' /etc/sysctl.conf
sysctl -p

# Update firewall rules
iptables -t nat -A POSTROUTING -o eth0 -j MASQUERADE
iptables -A INPUT -i eth0 -p tcp --dport 1723 -j ACCEPT
iptables -A INPUT -i eth0 -p gre -j ACCEPT

# Save firewall rules
iptables-save > /etc/iptables.rules

# Enable and start the PPTP server
systemctl enable pptpd
systemctl restart pptpd

echo "PPTP server installation and configuration completed."
