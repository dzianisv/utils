#!/bin/sh

SCRIPT_PATH="/usr/bin/configurator"
CRON_JOB_PATH="/etc/crontabs/root"

if ! command -v curl || ! command -v jq; then
    opkg update
    opkg install curl jq
fi

# Create the installation script
cat << 'EOF' > "$SCRIPT_PATH"
#!/bin/sh

# Define the URL and script paths
CONFIGURATION_URL=$(configurator.@general[0].url)

# Function to find wireless interface by SSID
find_wireless_interface_by_ssid() {
    SSID=$1
    # Get the list of wireless interfaces
    interfaces=$(uci show wireless | grep "=wifi-iface" | cut -d. -f2 | cut -d'=' -f1)

    # Iterate over the interfaces
    for interface in $interfaces; do
        # Get the SSID of the current interface
        ssid=$(uci get wireless.$interface.ssid)

        # Check if the SSID matches the desired value
        if [[ "$ssid" == "$SSID" ]]; then
            echo "$interface"
        fi
    done
}

# Function to disable wireless interface by SSID
disable_wireless_interface_by_ssid() {
    echo "Disabling $SSID"
    interface=$(find_wireless_interface_by_ssid "$1")
    uci set "wireless.$interface.disabled=1"
    uci commit wireless
}

# Function to enable wireless interface by SSID
enable_wireless_interface_by_ssid() {
    echo "Enabling $SSID"
    interface=$(find_wireless_interface_by_ssid "$1")
    uci set "wireless.$interface.disabled=0"
    uci commit wireless
}

# Function to configure
configure() {
    configuration=$(curl "$CONFIGURATION_URL")
    echo "Got configuration: $configuration"
    for ssid in $( echo "$configuration" | jq -r ".wireless | keys[]" ); do
        enabled=$( echo "$configuration" | jq -r ".wireless.$ssid.enabled" )
        if [[ "$enabled" == "true" ]]; then
            enable_wireless_interface_by_ssid "$ssid"
        else
            disable_wireless_interface_by_ssid "$ssid"
        fi
    done
}

configure
EOF

# Set permissions for the installation script
chmod +x "$SCRIPT_PATH"


# Set the desired interval in seconds
INTERVAL=$(( 5 * 60 ))
# Create the cron job file
cat <<EOF > "$CRON_JOB_PATH"
*/$INTERVAL * * * * $SCRIPT_PATH >/dev/null 2>&1
EOF

# Set permissions for the cron job file
chmod 0644 "$CRON_JOB_PATH"

# Restart the cron service
/etc/init.d/cron restart

if [[ -z "$(uci get configurator.@general[0].url)" ]]; then
    echo -n "Type in json configuratio URL: "
    read URL
    cat << EOF > /etc/config/configurator
config general
    option url "$URL"
EOF
fi