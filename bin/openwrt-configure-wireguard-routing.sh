#!/bin/sh
# hot to install:
# cat > /tmp/configure.sh && sh -x /tmp/configure.sh

# This OpenWrt configuration script automates the setup of guest networking using 'guestNetwork' routing table
# and WireGuard VPN routing for selective bypassing for *.BY and youtube.com subnets.

set -eu
# Confiugre the WAN interface, 3g network interface is used by default
WAN_INTERFACE=3g-3g
INCLUDE_FILE=/etc/hotplug.d/iface/common

# guest network routing rules will be added to this table
TABLE=guestNetwork

if ! grep "$TABLE" < /etc/iproute2/rt_tables; then
    echo "100 $TABLE" >> /etc/iproute2/rt_tables
fi

cat << EOF > "$INCLUDE_FILE"
WAN_INTERFACE=$WAN_INTERFACE

EOF

cat << EOF > /etc/hotplug.d/iface/99-guestNetwork
#!/bin/sh

source "/etc/hotplug.d/iface/common"
set -euo pipefail

NETWORK=192.168.42.0/24

if [ "\$ACTION" = "ifup" ] || [[ "\$INTERFACE" =~ ^br-guest.*$ ]]; then
    ip rule add from "\$NETWORK" lookup "$TABLE"
    ip route add "\$NETWORK" dev "\$INTERFACE"
fi

if [ "\$INTERFACE" = "\$WAN_INTERFACE"] && [ "\$ACTION" = "ifup" ]; then
    ip route add default dev "\$WAN_INTERFACE" table "$TABLE"
fi

EOF
chmod a+x /etc/hotplug.d/iface/99-guestNetwork


cat << EOF > /etc/hotplug.d/iface/99-wireguard
#!/bin/sh

source "$INCLUDE_FILE"

if [ "\$ACTION" != 'ifup' ] || [[ ! "\$INTERFACE" =~ ^wg[0-9]+$ ]]; then
	exit 0
fi

by_networks=\$(curl https://noc.datahata.by/free.txt)
youtube_networks=\$(curl https://raw.githubusercontent.com/touhidurrr/iplist-youtube/main/ipv4_list.txt)

for network in \$networks \$youtube_networks; do
    ip route add "\$network" dev "\$WAN_INTERFACE"
done

ip route del default
ip route add default via 10.0.0.1
EOF

chmod a+x /etc/hotplug.d/iface/99-wireguard
