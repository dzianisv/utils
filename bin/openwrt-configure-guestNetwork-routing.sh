#!/bin/sh
# how to configure:
#
# cat > /tmp/configure.sh && sh -x /tmp/configure.sh
#
# This OpenWrt configuration script automates the setup of guest networking using 'guestNetwork' routing table
# and WireGuard VPN routing for selective bypassing for *.BY and youtube.com subnets.
# Wirguard network has to be named like wg0-wg9 and `uci set newtwork.wg0.gateway=` has to be set correctly

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

if ! command -v curl; then
	opkg update
	opkg install -y curl
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

if [[ ! "$INTERFACE" =~ ^wg[0-9]+$ ]]; then
	exit 0
fi

gateway=$(uci get network.$INTERFACE.gateway)

if [ -z "$gateway" ]; then
	echo "Gateway for $INTERFACE is not set. Example: uci set network.$INTERFACE.gateway=10.0.0.1 && uci commit network" >&2
	exit 1
fi

resolve_ip() {
  domain=$1
  nslookup $domain 1.1.1.1 | awk '/^Address: / { print $2 }' | tail -n1
}

if [[ "$ACTION" = "ifup" ]]; then
	bypass_hosts=""
	for bypass_domain in kufar.by; do
		for _ in {1..16}; do
			ip=$(resolve_ip "$bypass_domain")
			if [[ -z "$ip" ]] ||  expr "$bypass_hosts" : ".*$ip.*"; then
				continue
			fi
			bypass_hosts="$bypass_hosts $ip"
			ip route add "$ip" dev "$WAN_INTERFACE"
		done
	done

	bypass_networks=$(curl https://noc.datahata.by/free.txt)
	youtube_networks=$(curl https://raw.githubusercontent.com/touhidurrr/iplist-youtube/main/ipv4_list.txt)

	for network in $bypass_networks $youtube_networks; do
    		ip route add "$network" dev "$WAN_INTERFACE" 2> /dev/null
	done

	prev_default_route=$(ip route show | grep default)
	ip route del default
	ip route add $prev_default_route metric 500
    ip route add "$gateway" dev "$INTERFACE"
	ip route add default via "$gateway"

elif [[ "$ACTION" = "ifdown" ]]; then
	echo "VPN is down :("
fi
EOF

chmod a+x /etc/hotplug.d/iface/99-wireguard