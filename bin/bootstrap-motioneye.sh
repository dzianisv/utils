#!/bin/sh -xe
apt update -yq
apt install -yq ssh curl motion ffmpeg v4l-utils python2 libffi-dev libzbar-dev libzbar0 python2-dev libssl-dev libcurl4-openssl-dev libjpeg-dev
command -v pip2 || curl https://bootstrap.pypa.io/pip/2.7/get-pip.py | python2

pip2 install motioneye

install -d -m 0755 /etc/motioneye
install -m 0644 /usr/local/share/motioneye/extra/motioneye.conf.sample /etc/motioneye/motioneye.conf

install -d -m 0755 /var/lib/motioneye
install -m 0644 /usr/local/share/motioneye/extra/motioneye.systemd-unit-local /etc/systemd/system/motioneye.service

systemctl daemon-reload
systemctl enable --now motioneye

apt install -yq avahi-daemon
curl "https://raw.githubusercontent.com/lathiat/avahi/master/avahi-daemon/ssh.service" > /etc/avahi/services/ssh.service
systemctl enable --now avahi-daemon

if ! command -v tailscale; then
    curl -fsSL "https://pkgs.tailscale.com/stable/ubuntu/jammy.noarmor.gpg" -o /usr/share/keyrings/tailscale-archive-keyring.gpg'
    curl -fsSL "https://pkgs.tailscale.com/stable/ubuntu/jammy.tailscale-keyring.list" -o /etc/apt/sources.list.d/tailscale.list'
    apt-get update
    apt-get install -yq tailscale 
    curl "https://raw.githubusercontent.com/lathiat/avahi/master/avahi-daemon/ssh.service" > /etc/avahi/services/ssh.services
    tailscale up
fi