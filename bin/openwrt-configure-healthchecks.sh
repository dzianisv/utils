#!/bin/sh

SCRIPT_PATH=/usr/bin/healthchecks

set -euo pipefail

# Create the HTTP GET script
cat << 'EOF' > "$SCRIPT_PATH"
#!/bin/sh
URL=$(uci get healthchecks.@healthchecks[0].url)
wget -q -O /dev/null "$URL"
EOF

chmod 0755 "$SCRIPT_PATH"

if [[ ! -f /etc/config/healthchecks ]]; then
    if [[ -z "${UUID:-}" ]]; then
        echo "UUID is not set"
        exit 1
    fi

    # Create the UCI config
    cat << "EOF" > /etc/config/healthchecks
config healthchecks
    option url 'https://hc-ping.com/$UUID'
EOF
fi

CRON_JOB_PATH="/etc/crontabs/root"
# Create the cron job to run script each 10m
cat <<EOF >> "$CRON_JOB_PATH"
*/10 * * * * $SCRIPT_PATH
EOF

# Set permissions for the cron job file
chmod 0644 "$CRON_JOB_PATH"

# Restart the cron service
/etc/init.d/cron restart