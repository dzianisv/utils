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

if ! command -v kubectl; then
    curl -fsSLo /usr/share/keyrings/kubernetes-archive-keyring.gpg https://packages.cloud.google.com/apt/doc/apt-key.gpg
    echo "deb [signed-by=/usr/share/keyrings/kubernetes-archive-keyring.gpg] https://apt.kubernetes.io/ kubernetes-xenial main" > /etc/apt/sources.list.d/kubernetes.list
    apt-get update
    apt-get install -y kubectl
fi

if ! command -v tsh; then
    curl https://deb.releases.teleport.dev/teleport-pubkey.asc -o /usr/share/keyrings/teleport-archive-keyring.asc
    source /etc/os-release
    echo "deb [signed-by=/usr/share/keyrings/teleport-archive-keyring.asc] https://apt.releases.teleport.dev/${ID?} ${VERSION_CODENAME?} stable/v10" > /etc/apt/sources.list.d/teleport.list
    apt update -yq
    apt-get install teleport
fi


if ! command -v tailscale; then
    curl -fsSL "https://pkgs.tailscale.com/stable/ubuntu/jammy.noarmor.gpg" -o /usr/share/keyrings/tailscale-archive-keyring.gpg
    curl -fsSL "https://pkgs.tailscale.com/stable/ubuntu/jammy.tailscale-keyring.list" -o /etc/apt/sources.list.d/tailscale.list
    apt-get update
    apt-get install -yq tailscale
fi

if ! command -v kubie; then
  curl "https://github.com/sbstp/kubie/releases/download/v0.19.0/kubie-linux-amd64" -Lo /usr/local/bin/kubie
  chmod a+x /usr/local/bin/kubie
fi

if ! command -v twingate; then
    curl -s https://binaries.twingate.com/client/linux/install.sh | bash
fi


apt install -y vim sshfs gnupg2 docker.io  golang g++ clang zeal python3 python3-pip pipenv nodejs npm python3
gpasswd -a $(id -u -n) docker

