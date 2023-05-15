#!/bin/sh
opkg update
opkg install libustream-mbedtls

# Create the daemon script
cat << 'EOF' > /etc/init.d/healthchecks
#!/bin/sh /etc/rc.common

START=99
STOP=01

USE_PROCD=1
PROG=/usr/bin/healthchecks
URL=$(uci get healthchecks.@healthchecks[0].url)

start_service() {
    procd_open_instance
    procd_set_param command $PROG $URL
    procd_set_param respawn
    procd_close_instance
}

stop_service() {
    killall healthchecks
}
EOF

chmod +x /etc/init.d/healthchecks

# Create the HTTP GET script
cat << 'EOF' > /usr/bin/healthchecks
#!/bin/sh

URL=$1

while true; do
    wget -q -O /dev/null "\$URL"
    sleep 3600
done
EOF

chmod +x /usr/bin/healthchecks

# Create the UCI config
# Replace https by http if there is not space for mbedtls
cat << 'EOF' > /etc/config/healthchecks
config healthchecks
    option url 'https://hc-ping.com/<uuid>'
EOF

# Enable and start the service
/etc/init.d/healthchecks enable
/etc/init.d/healthchecks start
