#!/bin/sh
set -eu


if [[ $(uname) == "Darwin" ]]; then
  GOPATH=${GOPATH:-~/go}
  export PATH="${PATH}:${GOPATH}/bin"

  go install tailscale.com/cmd/tailscale{,d}@main
  sudo tailscaled install-system-daemon
  sudo tailscale up
else
  curl -fsSL https://pkgs.tailscale.com/stable/ubuntu/jammy.noarmor.gpg | sudo tee /usr/share/keyrings/tailscale-archive-keyring.gpg >/dev/null
  curl -fsSL https://pkgs.tailscale.com/stable/ubuntu/jammy.tailscale-keyring.list | sudo tee /etc/apt/sources.list.d/tailscale.list
  sudo apt-get update
  sudo apt-get install tailscale
  sudo tailscale up
fi
