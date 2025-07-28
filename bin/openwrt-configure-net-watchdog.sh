#!/bin/sh

if ! command -v curl; then
    opkg update
    optk install curl
fi

WATCHDOG_SCRIPT=/usr/bin/watchdog.sh

cat << 'EOF' > "$WATCHDOG_SCRIPT"
#!/bin/sh
set -euo pipefail

watchdog_file=/var/run/watchdog

reload() {
    for interface in $(uci show network | grep '=interface' | sed -n 's/=interface//p' | cut -d'.' -f2)
    do
        if [[ "$interface" =~ wwan ]]; then
            echo "$interface"
            ifdown "$interface"
            ifup "$interface"
        fi
    done
}

status_code=$(curl -s -o /dev/null -w "%{http_code}" "connectivitycheck.gstatic.com/generate_204")

if [ "$status_code" != 204 ]; then
    modification_time=$(stat -f %Y "$watchdog_file" || echo 0)
    now=$(date +%s)
    time_passed=$((now - modification_time))
    echo "${time_passed}s passed since last network restart"
    if [[ "$time_passed" -gt 600 ]]; then
        touch "$watchdog_file"
        reload
    fi
fi
EOF

chmod a+x "$WATCHDOG_SCRIPT"

# Define the cron job line
CRON_JOB="*/1 * * * * $WATCHDOG_SCRIPT"

if  [[ ! "$(crontab -l)" =~ $WATCHDOG_SCRIPT ]] ; then
    # Append the cron job line to the current user's crontab
    (crontab -l 2>/dev/null; echo "$CRON_JOB" ) | crontab -
    # Verify it was added
    crontab -l
fi
