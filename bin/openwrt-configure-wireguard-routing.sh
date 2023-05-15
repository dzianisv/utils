#!/bin/sh
# how to configure:
#
# cat > /tmp/configure.sh && sh -x /tmp/configure.sh

# This OpenWrt configuration script automates the setup of guest networking using 'guestNetwork' routing table
# and WireGuard VPN routing for selective bypassing for *.BY and youtube.com subnets.

set -eu
# Confiugre the WAN interface, 3g network interface is used by default
WAN_INTERFACE=3g-3g
GUEST_INTERFACE=br-guestLan # TODO: read from the /etc/config/networks
GUEST_NETWORK=192.168.42.0/24

INCLUDE_FILE=/etc/hotplug.d/iface/common

# guest network routing rules will be added to this table
TABLE=guestNetwork

if ! grep "$TABLE" < /etc/iproute2/rt_tables; then
    echo "100 $TABLE" >> /etc/iproute2/rt_tables
fi

cat << EOF > "$INCLUDE_FILE"
WAN_INTERFACE=$WAN_INTERFACE
OPENWRT_WAN_INTERFACE=\${WAN_INTERFACE##*-}
EOF

cat << EOF > /etc/hotplug.d/iface/99-guestNetwork
#!/bin/sh

source "$INCLUDE_FILE"
set -uo pipefail

LOCAL_INTERFACE=$GUEST_INTERFACE
NETWORK=$GUEST_NETWORK

TABLE=$TABLE

echo \$ACTION \$INTERFACE >> /tmp/hotplug-iface.log

if [ ! "\$ACTION" = "ifup" ]; then
    exit 0
fi

if [[ "\$INTERFACE" = \${LOCAL_INTERFACE##*-}  ]]; then
    if ! ip rule show | grep "from \$NETWORK"; then
        ip rule add from "\$NETWORK" lookup \$TABLE
    fi
    ip route add "\$NETWORK" dev "\$LOCAL_INTERFACE" table \$TABLE || :
fi

if [[ "\$INTERFACE" = \${WAN_INTERFACE##*-} ]]; then
    ip route add default dev "\$WAN_INTERFACE" table \$TABLE || :
fi
EOF
chmod a+x /etc/hotplug.d/iface/99-guestNetwork


cat << EOF > /etc/hotplug.d/iface/99-wireguard
#!/bin/sh
source "/etc/hotplug.d/iface/common"

if [[ ! "\$INTERFACE" =~ ^wg[0-9]+$ ]]; then
	exit 0
fi


if [[ "\$ACTION" = "ifup" ]]; then
	by_networks=\$(curl https://noc.datahata.by/free.txt)
	youtube_networks=\$(curl https://raw.githubusercontent.com/touhidurrr/iplist-youtube/main/ipv4_list.txt)

	for network in \$networks \$youtube_networks; do
    		ip route add "\$network" dev "\$WAN_INTERFACE"
	done

	ip route del default
	ip route add default via 10.0.0.1
elif [[ "\$ACTION" = "ifdown" ]]; then
	ip route add default dev "\$WAN_INTERFACE"
fi
EOF



chmod a+x /etc/hotplug.d/iface/99-wireguard
