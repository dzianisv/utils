#!/bin/sh
set -eu

apt install -yq apt-transport-https curl

if ! command -v brave-browser ; then
    curl -fsSLo /usr/share/keyrings/brave-browser-archive-keyring.gpg "https://brave-browser-apt-release.s3.brave.com/brave-browser-archive-keyring.gpg"
    echo "deb [signed-by=/usr/share/keyrings/brave-browser-archive-keyring.gpg arch=amd64] https://brave-browser-apt-release.s3.brave.com/ stable main"| tee /etc/apt/sources.list.d/brave-browser-release.list
    apt update -yq && apt install -yq brave-browser
fi 

if ! command -v signal-desktop; then
    curl -Lo "/usr/share/keyrings/signal-desktop-keyring.gpg" "https://updates.signal.org/desktop/apt/keys.asc"
    echo 'deb [arch=amd64 signed-by=/usr/share/keyrings/signal-desktop-keyring.gpg] https://updates.signal.org/desktop/apt xenial main' | tee -a /etc/apt/sources.list.d/signal-xenial.list
    apt update -yq && apt install -yq signal-desktop
fi

if ! command -v session-desktop; then
    curl -Lo /tmp/session-desktop.deb "https://github.com/oxen-io/session-desktop/releases/download/v1.8.6/session-desktop-linux-amd64-1.8.6.deb"
    trap "rm /tmp/session-desktop.deb" EXIT
    apt install -y /tmp/session-desktop.deb
fi

if ! command -v yt-dlp; then
    curl "https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp" > /usr/local/bin/yt-dlp
    chmod a+x /usr/local/bin/yt-dlp
fi

if ! command -v code; then
    curl -Lo "/etc/apt/keyrings/packages.microsoft.gpg" https://packages.microsoft.com/keys/microsoft.gpg
    echo "deb [arch=amd64,arm64,armhf signed-by=/etc/apt/keyrings/packages.microsoft.gpg] https://packages.microsoft.com/repos/code stable main" | tee /etc/apt/sources.list.d/vscode.list
    apt update -yq
    apt install -yq code
fi

if ! command -v lxc; then
    snap install lxd
    gpasswd -a $(id -u -n) lxd
fi

apt install -y vim ffmpeg gocryptfs sshfs gnupg2 pass iptables-persistent docker.io virtualbox
gpasswd -a $(id -u -n) docker
gpasswd -a $(id -u -n) vboxusers
