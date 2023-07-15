#!/bin/sh
# how to configure:
#
# cat > /tmp/configure.sh && sh -x /tmp/configure.sh
#
# This OpenWrt configuration script automates the setup of networking using '$PRIVATE_NETWORK_TABLE' routing PRIVATE_NETWORK_TABLE
# and WireGuard VPN routing for selective bypassing for *.BY and youtube.com subnets.
# Wirguard network has to be named like wg0-wg9 and `uci set newtwork.wg0.gateway=` has to be set correctly

set -eu

# Confiugre the WAN interface, 3g network interface is used by default
WAN_INTERFACE=3g-3g
PRIVATE_NETWORK_INTERFACE_NAME="privateLan"
PRIVATE_NETWORK_INTERFACE=br-privateLan # TODO: read from the /etc/config/networks
PRIVATE_NETWORK=192.168.64.1/24
PRIVATE_NETWORK_TABLE=$PRIVATE_NETWORK_INTERFACE_NAME

# network routing rules will be added to this PRIVATE_NETWORK_TABLE

# uci add_list firewall.cfg02dc81.network='lan'
# uci add_list firewall.cfg02dc81.network="$PRIVATE_NETWORK_INTERFACE_NAME"

# # /etc/config/network
uci set network.privateLan=interface
uci set network.privateLan.proto='static'
uci set network.privateLan.ipaddr="${PRIVATE_NETWORK%/*}"
uci set network.privateLan.netmask='255.255.255.0'
uci set network.privateLan.device="$PRIVATE_NETWORK_INTERFACE"
uci set network.privateLan.type='bridge'

# /etc/config/dhcp
uci set dhcp.privateLan=dhcp
uci set dhcp.privateLan.interface="$PRIVATE_NETWORK_INTERFACE_NAME"
uci set dhcp.privateLan.start='100'
uci set dhcp.privateLan.limit='150'
uci set dhcp.privateLan.leasetime='12h'

# # /etc/config/wireless
# uci set wireless.wifinet1.network="$PRIVATE_NETWORK_INTERFACE_NAME"

# uci commit dhcp
# uci commit network

if ! grep "$PRIVATE_NETWORK_TABLE" < /etc/iproute2/rt_tables; then
    echo "100 $PRIVATE_NETWORK_TABLE" >> /etc/iproute2/rt_tables
fi

if ! command -v curl; then
	opkg update
	opkg install -y curl
fi

cat << EOF > /etc/hotplug.d/iface/common
WAN_INTERFACE=$WAN_INTERFACE
OPENWRT_WAN_INTERFACE=\${WAN_INTERFACE##*-}
PRIVATE_NETWORK_INTERFACE=$PRIVATE_NETWORK_INTERFACE
PRIVATE_NETWORK_INTERFACE_ADDRESS=$PRIVATE_NETWORK
PRIVATE_NETWORK_TABLE=$PRIVATE_NETWORK_TABLE
LOG_FILE=/tmp/hotplug-iface.log

log() {
	echo "\$(date -Ins) \$@" >> "\$LOG_FILE"
}

exec_log() {
	log "\$@"
	"\$@"
}

resolve_ip() {
  domain=\$1
  nslookup \$domain 1.1.1.1 | awk '/^Address: / { print \$2 }' | tail -n1
}

EOF

cat << 'EOF' > /etc/hotplug.d/iface/99-privateNetwork
#!/bin/sh
source "/etc/hotplug.d/iface/common"
set -uo pipefail

log $ACTION $INTERFACE

function get_network() {
    ip=$1
    # Extract the base IP and the CIDR prefix (if any)
    base_ip=${ip%/*}
    cidr_prefix=${ip#*/}

    # Check if CIDR prefix exists, if not set to empty string
    if [ "$base_ip" == "$cidr_prefix" ]; then
        cidr_prefix=""
    else
        cidr_prefix="/$cidr_prefix"
    fi

    # Replace the last octet with zero
    new_base_ip=$(echo "$base_ip" | sed -r 's/([0-9]+\.[0-9]+\.[0-9]+\.)[0-9]+/\10/')

    # Combine the new base IP with the CIDR prefix
    new_ip="$new_base_ip$cidr_prefix"

    echo $new_ip
}

if [ ! "$ACTION" = "ifup" ]; then
    exit 0
fi

if [[ "$INTERFACE" = ${PRIVATE_NETWORK_INTERFACE##*-}  ]]; then
    if ! ip rule show | grep "from $PRIVATE_NETWORK_INTERFACE_ADDRESS"; then
        exec_log ip rule add from "$PRIVATE_NETWORK_INTERFACE_ADDRESS" lookup $PRIVATE_NETWORK_TABLE
    fi
	network=$(get_network "$PRIVATE_NETWORK_INTERFACE_ADDRESS")
    exec_log ip route add "$network" dev "$PRIVATE_NETWORK_INTERFACE" table $PRIVATE_NETWORK_TABLE || :
fi

if [[ "$INTERFACE" = ${WAN_INTERFACE##*-} ]]; then
	exec_log ip route add default dev "$WAN_INTERFACE" table $PRIVATE_NETWORK_TABLE metrci 500 || :

	bypass_hosts=""
	for bypass_domain in kufar.by; do
		for _ in {1..16}; do
			ip=$(resolve_ip "$bypass_domain")
			if [[ -z "$ip" ]] ||  expr "$bypass_hosts" : ".*$ip.*"; then
				continue
			fi
			bypass_hosts="$bypass_hosts $ip"
			exec_log ip route add "$ip" dev "$WAN_INTERFACE" table $PRIVATE_NETWORK_TABLE || ::
		done
	done

	bypass_networks=$(curl https://noc.datahata.by/free.txt)
	for network in $bypass_networks; do
    	exec_log ip route add "$network" dev "$WAN_INTERFACE" table $PRIVATE_NETWORK_TABLE  2> /dev/null
	done
fi
EOF
chmod a+x /etc/hotplug.d/iface/99-privateNetwork


cat << 'EOF' > /etc/hotplug.d/iface/99-wireguard
#!/bin/sh
source "/etc/hotplug.d/iface/common"

if [[ ! "$INTERFACE" =~ ^wg.*$ ]]; then
	exit 0
fi

gateway=$(uci get network.$INTERFACE.gateway)

if [ -z "$gateway" ]; then
	echo "Gateway for $INTERFACE is not set. Example: uci set network.$INTERFACE.gateway=10.0.0.1 && uci commit network" >&2
	exit 1
fi

if [[ "$ACTION" = "ifup" ]]; then
	# prev_default_route=$(ip route show | grep default)
	# ip route del default table $PRIVATE_NETWORK_TABLE
	# ip route add $prev_default_route metric 500 table $PRIVATE_NETWORK_TABLE

    exec_log ip route add "$gateway" dev "$INTERFACE" table $PRIVATE_NETWORK_TABLE
	exec_log ip route add default via "$gateway" table $PRIVATE_NETWORK_TABLE
elif [[ "$ACTION" = "ifdown" ]]; then
	echo "VPN is down :("
fi
EOF

chmod a+x /etc/hotplug.d/iface/99-wireguard