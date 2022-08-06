#!/bin/sh
set -eu

apt install -yq apt-transport-https curl

if [ ! -e /usr/share/keyrings/brave-browser-archive-keyring.gpg ]; then
    curl -fsSLo /usr/share/keyrings/brave-browser-archive-keyring.gpg "https://brave-browser-apt-release.s3.brave.com/brave-browser-archive-keyring.gpg"
    echo "deb [signed-by=/usr/share/keyrings/brave-browser-archive-keyring.gpg arch=amd64] https://brave-browser-apt-release.s3.brave.com/ stable main"| tee /etc/apt/sources.list.d/brave-browser-release.list
fi 

if [ ! -e /usr/share/keyrings/signal-desktop-keyring.gpg ]; then
    curl -Lo "/usr/share/keyrings/signal-desktop-keyring.gpg" "https://updates.signal.org/desktop/apt/keys.asc"
    echo 'deb [arch=amd64 signed-by=/usr/share/keyrings/signal-desktop-keyring.gpg] https://updates.signal.org/desktop/apt xenial main' | tee -a /etc/apt/sources.list.d/signal-xenial.list
fi

sudo apt update

apt update -yq
apt install -y brave-browser signal-desktop

apt install -y vim ffmpeg gocryptfs sshfs gnupg2 pass iptables-persistent docker.io virtualbox
snap install --classic code
snap install lxd
gpasswd -a $(id -u -n) docker
gpasswd -a $(id -u -n) lxd
gpasswd -a $(id -u -n) vboxusers

curl "https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp" > /usr/local/bin/yt-dlp
chmod a+x /usr/local/bin/yt-dlp


if ! command -v session-desktop; then
    curl -o /tmp/session-desktop.deb "https://github.com/oxen-io/session-desktop/releases/download/v1.8.6/session-desktop-linux-amd64-1.8.6.deb"
    trap "rm /tmp/session-desktop.deb" EXIT
    apt install -y /tmp/session-desktop.deb
fi