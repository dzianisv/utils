#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 1 ]]; then
  echo "Usage: $0 NETWORK_CIDR"
  exit 1
fi

NETWORK="$1"
USER="root"
PASS="1234"

# Dependencies
for cmd in nmap sshpass; do
  if ! command -v "$cmd" >/dev/null; then
    echo "Install $cmd via Homebrew: brew install $cmd"
    exit 1
  fi
done

echo "Scanning $NETWORK for SSH (port 22)…"
# -n: no DNS; -R: force reverse-DNS (per your request); --open: only show open ports
NMAP_OUT=$(nmap -p22 -R -n --open -oG - "$NETWORK")

# Extract only the IPs with port 22/open
SSH_TARGETS=$(printf '%s\n' "$NMAP_OUT" \
             | awk '$1=="Host:" && $3~/22\/open/ { print $2 }')

if [[ -z "$SSH_TARGETS" ]]; then
  echo "No SSH hosts found in $NETWORK."
  exit 0
fi

echo "Discovered SSH hosts:"
printf "  %s\n" $SSH_TARGETS
echo

while IFS= read -r IP; do
  printf "Trying %s@%s… " "$USER" "$IP"
  if sshpass -p"$PASS" ssh \
       -oBatchMode=yes \
       -oStrictHostKeyChecking=no \
       -oConnectTimeout=5 \
       "$USER@$IP" \
       'echo "✔ Connected to $(hostname)"' \
       &>/dev/null; then
    echo "SUCCESS"
  else
    echo "FAIL"
  fi
done <<< "$SSH_TARGETS"
