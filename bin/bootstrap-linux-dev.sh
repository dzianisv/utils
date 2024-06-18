#!/bin/bash
set -eu

apt install -yq apt-transport-https curl gnupg

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


if ! command -v tailscale; then
    curl -fsSL "https://pkgs.tailscale.com/stable/ubuntu/jammy.noarmor.gpg" -o /usr/share/keyrings/tailscale-archive-keyring.gpg
    curl -fsSL "https://pkgs.tailscale.com/stable/ubuntu/jammy.tailscale-keyring.list" -o /etc/apt/sources.list.d/tailscale.list
    apt-get update
    apt-get install -yq tailscale
fi

apt install -y vim sshfs gnupg2 docker.io  golang g++ clang zeal python3 python3-pip pipenv nodejs npm python3
gpasswd -a $(id -u -n) docker

