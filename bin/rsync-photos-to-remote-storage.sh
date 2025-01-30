#!/bin/bash
set -euo pipefail

discover_host() {
    local hostname="$1"
    if ping -c 1 -t 1 "$hostname.local" 2>&1 >/dev/null; then
        echo "$hostname.local"
        return 0
    fi

    while read -r ip name _; do
        if [[ "$name" == "$hostname" ]]; then
            if ping -c 1 -t 1 $ip 2>&1 >/dev/null; then
                echo $ip
                return 0
            else
                return 1
            fi
        fi
    done < <(tailscale status)
    return 1
}

TARGET_HOSTNAME=${TARGET_HOSTNAME:-file-berry}

DISCOVERED_HOSTNAME=$(discover_host $TARGET_HOSTNAME)
SSH_HOST=${SSH_HOST:-root@$DISCOVERED_HOSTNAME}
echo $SSH_HOST
exec rsync --progress -rtl --remove-source-files -e "ssh -c chacha20-poly1305@openssh.com" ~/Desktop/PhotoDump/ "$SSH_HOST:/media/External5TB/Photography/"