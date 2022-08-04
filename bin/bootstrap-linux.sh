#!/bin/sh
set -eu

apt install -yq apt-transport-https curl
curl -fsSLo /usr/share/keyrings/brave-browser-archive-keyring.gpg https://brave-browser-apt-release.s3.brave.com/brave-browser-archive-keyring.gpg
echo "deb [signed-by=/usr/share/keyrings/brave-browser-archive-keyring.gpg arch=amd64] https://brave-browser-apt-release.s3.brave.com/ stable main"| tee /etc/apt/sources.list.d/brave-browser-release.list
apt update -yq
apt install -y brave-browser

apt install -y vim ffmpeg gocryptfs sshfs gnupg2 pass iptables-persistent docker.io virtualbox
snap install --classic code
snap install lxd
gpasswd -a $(id -u -n) docker
gpasswd -a $(id -u -n) lxd
gpasswd -a $(id -u -n) vboxusers