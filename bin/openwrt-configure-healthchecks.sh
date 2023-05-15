#!/bin/sh

set -euo pipefail

if [[ -z "${UUID:-}" ]]; then
    echo "UUID is not set"
    exit 1
fi

# Create the daemon script
cat << 'EOF' > /etc/init.d/healthchecks
#!/bin/sh /etc/rc.common

START=99
STOP=01

USE_PROCD=1
PROG=/usr/bin/healthchecks_script
URL=$(uci get healthchecks.@healthchecks[0].url)
INTERVAL=$(uci get healthchecks.@healthchecks[0].interval)

start_service() {
    procd_open_instance
    procd_set_param command $PROG $URL $INTERVAL
    procd_set_param respawn
    procd_close_instance
}

stop_service() {
    killall healthchecks_script
}
EOF

chmod +x /etc/init.d/healthchecks

# Create the HTTP GET script
cat << 'EOF' > /usr/bin/healthchecks_script
#!/bin/sh

URL=$1
INTERVAL=$2

while true; do
    wget -q -O /dev/null "$URL"
    sleep $INTERVAL
done
EOF

chmod +x /usr/bin/healthchecks_script

# Create the UCI config
cat << "EOF" > /etc/config/healthchecks
config healthchecks
    option url 'https://hc-ping.com/$UUID'
    option interval '10'
EOF

# Enable and start the service
/etc/init.d/healthchecks enable
/etc/init.d/healthchecks start
