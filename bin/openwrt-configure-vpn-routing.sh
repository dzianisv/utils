#!/bin/sh
# cat > /tmp/configure && sh -x /tmp/configure ; rm /tmp/configure
cat << 'EOF' > /etc/hotplug.d/iface/99-routing.sh
#!/bin/sh

if [[ ! "$INTERFACE" =~ ^wg[0-9]+$ ]]; then
	exit 0
fi


function get_wireless_managed_interface() {
    iw dev | awk '/Interface/ {interface=$2} /type managed/ {print interface; exit}'
}

function get_uplink_gateway() {
	uplink=$(get_wireless_managed_interface)
	ip route show | sed -n -e "s/^default via \\([0-9\\.]*\\) dev $uplink .*/\\1/p"
}

uplink_gateway=$(get_uplink_gateway)


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
			ip route add "$ip" via "$uplink_gateway" || :
		done
	done

	bypass_networks=$(curl https://noc.datahata.by/free.txt)

	for network in $bypass_networks; do
    		ip route add "$network" via $uplink_gateway 2> /dev/null || :
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

chmod a+x /etc/hotplug.d/iface/99-routing.sh