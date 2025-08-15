#!/bin/sh
set -eu




if [[ $(uname) == "Darwin" ]]; then
  GOPATH=${GOPATH:-~/go}
  export PATH="${PATH}:${GOPATH}/bin"
  if ! command -v go 2> /dev/null; then
    brew install go
  fi
  go install tailscale.com/cmd/tailscale{,d}@main
  sudo tailscaled install-system-daemon
  sudo tailscale up
else
  curl https://pkgs.tailscale.com/stable/ubuntu/jammy.noarmor.gpg | tee /usr/share/keyrings/tailscale-archive-keyring.gpg >/dev/null
  curl https://pkgs.tailscale.com/stable/ubuntu/jammy.tailscale-keyring.list | tee /etc/apt/sources.list.d/tailscale.list
  apt-get update -yq
  apt-get install -yqtailscale
  tailscale up
fi

ZeroTrust
eors