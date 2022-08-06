#!/bin/sh
set -eu

apt install -yq apt-transport-https curl

if ! command -v brave-browser ; then
    curl -fsSLo /usr/share/keyrings/brave-browser-archive-keyring.gpg "https://brave-browser-apt-release.s3.brave.com/brave-browser-archive-keyring.gpg"
    echo "deb [signed-by=/usr/share/keyrings/brave-browser-archive-keyring.gpg arch=amd64] https://brave-browser-apt-release.s3.brave.com/ stable main"| tee /etc/apt/sources.list.d/brave-browser-release.list
    apt update -yq && apt install -yq brave-browser
fi 

if ! command -v code; then
    curl -Lo "/etc/apt/keyrings/packages.microsoft.asc" https://packages.microsoft.com/keys/microsoft.asc
    echo "deb [arch=amd64,arm64,armhf signed-by=/etc/apt/keyrings/packages.microsoft.gpg] https://packages.microsoft.com/repos/code stable main" | tee /etc/apt/sources.list.d/vscode.list
    apt update -yq
    apt install -yq code
fi

if ! command -v kubectl; then
    curl -fsSLo /usr/share/keyrings/kubernetes-archive-keyring.gpg https://packages.cloud.google.com/apt/doc/apt-key.gpg
    echo "deb [signed-by=/usr/share/keyrings/kubernetes-archive-keyring.gpg] https://apt.kubernetes.io/ kubernetes-xenial main" | tee /etc/apt/sources.list.d/kubernetes.list
    apt-get update
    apt-get install -y kubectl
fi

if ! command -v tsh; then
    curl https://deb.releases.teleport.dev/teleport-pubkey.asc -o /usr/share/keyrings/teleport-archive-keyring.asc
    source /etc/os-release
    echo "deb [signed-by=/usr/share/keyrings/teleport-archive-keyring.asc] https://apt.releases.teleport.dev/${ID?} ${VERSION_CODENAME?} stable/v10" | tee /etc/apt/sources.list.d/teleport.list
    apt update -yq
    apt-get install teleport
fi

apt install -y vim sshfs gnupg2 docker.io  golang g++ clang zeal python3 python3-pip python3-pipenv node npm
gpasswd -a $(id -u -n) docker

