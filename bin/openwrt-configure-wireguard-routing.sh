#!/bin/sh
# hot to install:
# cat > /tmp/configure.sh && sh -x /tmp/configure.sh

# This OpenWrt configuration script automates the setup of guest networking using 'guestNetwork' routing table
# and WireGuard VPN routing for selective bypassing for *.BY and youtube.com subnets.

set -eu
# Confiugre the WAN interface, 3g network interface is used by default
WAN_INTERFACE=3g-3g
GUEST_INTERFACE=br-guestLan # TODO: read from the /etc/config/networks
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

source "$INCLUDE_FILE"
set -uo pipefail

get_nic_network() {
    address=\$(ip addr show \$1 | awk '/inet / {print \$2}')
    # Get IP address and CIDR netmask
    ipaddr=\$(echo \$1 | cut -d/ -f1)
    netmask=\$(echo \$1 | cut -d/ -f2)

    # Calculate network address
    echo \$ipaddr | IFS=. read -r i1 i2 i3 i4
    ipdec=\$(( (i1<<24) + (i2<<16) + (i3<<8) + i4 ))

    echo \$(printf "%d.%d.%d.%d" \$((~((1<<(32-netmask))-1) >> 24 & 0xFF)) \$((~((1<<(32-netmask))-1) >> 16 & 0xFF)) \$((~((1<<(32-netmask))-1) >> 8 & 0xFF)) \$((~((1<<(32-netmask))-1) & 0xFF)))
    netmaskdec=\$(( (m1<<24) + (m2<<16) + (m3<<8) + m4 )) | IFS=. read -r m1 m2 m3 m4

    netdec=\$(( ipdec & netmaskdec ))
    netaddr=\$(printf "%d.%d.%d.%d" \$((netdec>>24)) \$((netdec>>16&0xFF)) \$((netdec>>8&0xFF)) \$((netdec&0xFF)))

    echo "\${netaddr}/\${netmask}"
}

LOCAL_INTERFACE=$GUEST_INTERFACE
NETWORK=\$(get_nic_network "\$LOCAL_INTERFACE")

if [ "\$ACTION" = "ifup" ]; then
    if ! ip rule show | grep "from \$NETWORK"; then
        ip rule add from "\$NETWORK" lookup guestNetwork
    fi
    ip route add "\$NETWORK" dev "\$LOCAL_INTERFACE" table guestNetwork
    ip route add default dev "\$WAN_INTERFACE" table guestNetwork
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
