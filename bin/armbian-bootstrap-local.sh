#!/bin/bash

set -euo pipefail
curl -fsSL "https://pkgs.tailscale.com/stable/ubuntu/jammy.noarmor.gpg" -o /usr/share/keyrings/tailscale-archive-keyring.gpg
curl -fsSL "https://pkgs.tailscale.com/stable/ubuntu/jammy.tailscale-keyring.list" -o /etc/apt/sources.list.d/tailscale.list
apt-get update
apt-get install -yq tailscale avahi-daemon
curl "https://raw.githubusercontent.com/lathiat/avahi/master/avahi-daemon/ssh.service" > /etc/avahi/services/ssh.service


curl "https://download-cdn.resilio.com/2.7.3.1381/Debian/resilio-sync_2.7.3.1381-1_armhf.deb" > /tmp/resilio-sync.deb
apt install -yq /tmp/resilio-sync.deb'
systemctl enable --now resilio-sync
tailscale up

