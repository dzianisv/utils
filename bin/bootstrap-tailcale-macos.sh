#!/bin/sh
set -eu
GOPATH=${GOPATH:-~/go}
export PATH="${PATH}:${GOPATH}/bin"

go install tailscale.com/cmd/tailscale{,d}@main
sudo tailscaled install-system-daemon
sudo tailscale up

