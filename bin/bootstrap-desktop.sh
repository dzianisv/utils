#!/bin/sh
set -eu

apt install -yq apt-transport-https curl

if ! command -v brave-browser ; then
    curl -fsSLo /usr/share/keyrings/brave-browser-archive-keyring.gpg "https://brave-browser-apt-release.s3.brave.com/brave-browser-archive-keyring.gpg"
    echo "deb [signed-by=/usr/share/keyrings/brave-browser-archive-keyring.gpg arch=amd64] https://brave-browser-apt-release.s3.brave.com/ stable main"| tee /etc/apt/sources.list.d/brave-browser-release.list
    apt update -yq && apt install -yq brave-browser
fi 

if ! command -v signal-desktop; then
    curl -L "https://updates.signal.org/desktop/apt/keys.asc" | gpg2 --dearmor > "/usr/share/keyrings/signal-desktop-keyring.gpg"
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
    curl -L "https://packages.microsoft.com/keys/microsoft.asc" | gpg2 --dearmor > "/usr/share/keyrings/code.gpg"
    echo "deb [arch=amd64,arm64,armhf signed-by=/usr/share/keyrings/code.gpg] https://packages.microsoft.com/repos/code stable main" > /etc/apt/sources.list.d/vscode.list
    apt update -yq
    apt install -yq code
fi

if ! command -v rslsync; then
    curl "https://download-cdn.resilio.com/2.7.3.1381/Debian/resilio-sync_2.7.3.1381-1_amd64.deb" -o /tmp/rslsync.deb
    trap "rm /tmp/rslsync.deb" EXIT
    apt install /tmp/rslsync.deb
fi

if ! command -v tailscale; then
    curl -fsSL "https://pkgs.tailscale.com/stable/ubuntu/jammy.noarmor.gpg" -o /usr/share/keyrings/tailscale-archive-keyring.gpg
    curl -fsSL "https://pkgs.tailscale.com/stable/ubuntu/jammy.tailscale-keyring.list" -o /etc/apt/sources.list.d/tailscale.list
    apt-get update
    apt-get install -yq tailscale avahi-daemon
fi

if ! command -v lxc; then
    snap install lxd
    gpasswd -a $(id -u -n) lxd
fi

apt install -y vim ffmpeg gocryptfs sshfs gnupg2 pass iptable s-persistent docker.io virtualbox
apt install -yq libreoffice-gnome libreoffice-writer libreoffice-calc
apt isntall -yq pytnon3 pylint bpython
gpasswd -a $(id -u -n) docker
gpasswd -a $(id -u -n) vboxusers

# allow operations on PDF documents
sed -i 's/<policy domain="coder" rights="none" pattern="PDF" \/>/<plicy domain="coder" rights="read | write" pattern="PDF" \/>/g' /etc/ImageMagick-6/policy.xml

if grep 'export PS1="\$(ip netns identify) $PS1"' ~/.bashrc;
    echo 'export PS1="\$(ip netns identify) $PS1"' >> ~/.bashrc
fi