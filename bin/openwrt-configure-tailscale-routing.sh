#!/bin/sh
#
# kill_switch_tailscale.sh
# Enforce a VPN-only “kill‑switch” on OpenWrt via Tailscale exit node
# Usage: sh /root/kill_switch_tailscale.sh

set -e

# 1. Ensure root privileges
if [ "$(id -u)" -ne 0 ]; then
  echo "Error: This script must be run as root" >&2
  exit 1
fi

# 2. Restart Tailscale with the exit node
echo "Bringing down any existing Tailscale session..."
tailscale down || true

EXIT_NODE="raspberrypi-paloalto-ca"   # 100.83.154.46
echo "Bringing up Tailscale, routing all traffic through exit node ${EXIT_NODE}..."
tailscale up \
  --exit-node="${EXIT_NODE}" \
  --exit-node-allow-lan-access      # ensures LAN clients use the exit node :contentReference[oaicite:3]{index=3}

# 3. Configure firewall for kill‑switch
echo "Configuring firewall rules..."

uci batch <<EOF
# a) Create a dedicated Tailscale zone on tailscale0
add firewall zone
set firewall.@zone[-1].name='tailscale'
set firewall.@zone[-1].input='ACCEPT'
set firewall.@zone[-1].output='ACCEPT'
set firewall.@zone[-1].forward='ACCEPT'
set firewall.@zone[-1].masq='1'      # enable NAT on the VPN interface :contentReference[oaicite:4]{index=4}
set firewall.@zone[-1].mtu_fix='1'    # clamp MSS for WireGuard :contentReference[oaicite:5]{index=5}
add_list firewall.@zone[-1].device='tailscale0'

# b) Remove default LAN→WAN forwarding (if present)
#    This blocks any direct internet egress outside the VPN tunnel :contentReference[oaicite:6]{index=6}
#    (We search for and delete each matching rule)
EOF

# Delete any existing lan→wan forwarding entries
for idx in $(uci show firewall | grep "\[.*\]\.forwarding" -B1 | \
             grep "src='lan'.*dest='wan'" -n | cut -d: -f1); do
  uci delete firewall.@forwarding["$((idx-1))"]
done

# c) Block any remaining LAN→WAN traffic explicitly
uci batch <<EOF
add firewall rule
set firewall.@rule[-1].name='killswitch_drop_lan_wan'
set firewall.@rule[-1].src='lan'
set firewall.@rule[-1].dest='wan'
set firewall.@rule[-1].target='DROP'   # enforce kill‑switch :contentReference[oaicite:7]{index=7}

# d) Allow only LAN→tailscale forwarding
add firewall forwarding
set firewall.@forwarding[-1].src='lan'
set firewall.@forwarding[-1].dest='tailscale'
commit firewall
EOF

# 4. Reload firewall
echo "Reloading firewall..."
/etc/init.d/firewall reload

# 5. Verification
echo "Verification:"
echo "- Default route:"
ip route show default   # should point via exit node on tailscale0
echo "- Tailscale status:"
tailscale status        # confirm exit


