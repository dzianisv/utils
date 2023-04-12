#!/bin/bash
set -eu

host=${1:-bananapi.local}
user=root
ssh-copy-id "${user}@$host"

run() {
    ssh "${user}@${host}" "$*"
}

run 'curl -fsSL "https://pkgs.tailscale.com/stable/ubuntu/jammy.noarmor.gpg" -o /usr/share/keyrings/tailscale-archive-keyring.gpg'
run 'curl -fsSL "https://pkgs.tailscale.com/stable/ubuntu/jammy.tailscale-keyring.list" -o /etc/apt/sources.list.d/tailscale.list'
run 'apt-get update'
run 'apt-get install -yq tailscale avahi-daemon'
run 'curl "https://raw.githubusercontent.com/lathiat/avahi/master/avahi-daemon/ssh.service" > /etc/avahi/services/ssh.service'

run 'curl "https://download-cdn.resilio.com/2.7.3.1381/Debian/resilio-sync_2.7.3.1381-1_armhf.deb" > /tmp/resilio-sync.deb'
run 'apt install -yq /tmp/resilio-sync.deb'
run 'systemctl enable --now resilio-sync'
run 'tailscale up'

