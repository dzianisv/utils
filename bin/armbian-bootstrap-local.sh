#!/bin/bash
set -euo pipefail

if ! command resilio-sync; then
    curl "https://download-cdn.resilio.com/2.7.3.1381/Debian/resilio-sync_2.7.3.1381-1_armhf.deb" > /tmp/resilio-sync.deb
    apt install -yq /tmp/resilio-sync.deb
    systemctl enable --now resilio-sync
    echo "fs.inotify.max_user_watches=524288" > /etc/sysctl.d/inotify.conf
    sysctl -p /etc/sysctl.d/inotify.conf
fi

if ! tailscale status; then
    curl -fsSL "https://pkgs.tailscale.com/stable/ubuntu/jammy.noarmor.gpg" -o /usr/share/keyrings/tailscale-archive-keyring.gpg
    curl -fsSL "https://pkgs.tailscale.com/stable/ubuntu/jammy.tailscale-keyring.list" -o /etc/apt/sources.list.d/tailscale.list
    tailscale up
fi

if ! command -v avahi-daemon; then
    apt-get update
    apt-get install -yq tailscale avahi-daemon
    curl "https://raw.githubusercontent.com/lathiat/avahi/master/avahi-daemon/ssh.service" > /etc/avahi/services/ssh.service
fi