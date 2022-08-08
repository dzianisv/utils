#!/bin/bash
set -eu

apt install -yq apt-transport-https curl gnupg2

if ! command -v brave-browser ; then
    curl -fsSLo /usr/share/keyrings/brave-browser-archive-keyring.gpg "https://brave-browser-apt-release.s3.brave.com/brave-browser-archive-keyring.gpg"
    echo "deb [signed-by=/usr/share/keyrings/brave-browser-archive-keyring.gpg arch=amd64] https://brave-browser-apt-release.s3.brave.com/ stable main" > /etc/apt/sources.list.d/brave-browser-release.list
    apt update -yq && apt install -yq brave-browser
fi 

if ! command -v code; then
    curl https://packages.microsoft.com/keys/microsoft.asc | apt-key add -
    echo "deb [arch=amd64,arm64,armhf] https://packages.microsoft.com/repos/code stable main" > /etc/apt/sources.list.d/vscode.list
    apt update -yq
    apt install -yq code
fi

if ! command -v torctl; then
    curl -Lo /tmp/torctl.deb "https://github.com/dzianisv/torctl/releases/download/1.0.2/torctl_1.0.2_all.deb"
    trap "rm /tmp/torctl.deb" EXIT
    apt install /tmp/torctl.deb
fi

apt install -y vim sshfs gnupg2 zeal python3 python3-pip pipenv nodejs npm python3-bpython
apt install -y libreoffice-calc libreoffice-gnome

gpasswd -a $(id -u -n) docker

prompt="export PS1=\"\$(curl -m3 api.ipify.org 2>/dev/null) \$PS1\""
if ! grep "${prompt}" ~/.bashrc; then
    echo "${prompt}" >> ~/.bashrc
fi