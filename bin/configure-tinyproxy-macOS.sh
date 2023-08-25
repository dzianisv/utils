#!/bin/bash

set -euo pipefail
# Create the configuration file
cat << EOF > /usr/local/etc/tinyproxy/tinyproxy.conf
User nobody
Group nobody
Port 8888
Timeout 600
DefaultErrorFile "/usr/local/share/tinyproxy/default.html"
Logfile "/usr/local/var/log/tinyproxy/tinyproxy.log"
LogLevel Info
PidFile "/usr/local/var/run/tinyproxy/tinyproxy.pid"
MaxClients 100
MinSpareServers 5
MaxSpareServers 20
StartServers 10
MaxRequestsPerChild 0
Allow 127.0.0.1
EOF

# Create the plist daemon file
cat << EOF > /Library/LaunchDaemons/com.tinyproxy.plist
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.tinyproxy</string>
    <key>Program</key>
    <string>/usr/local/bin/tinyproxy</string>
    <key>ProgramArguments</key>
    <array>
        <string>/usr/local/bin/tinyproxy</string>
        <string>-c</string>
        <string>/usr/local/etc/tinyproxy/tinyproxy.conf</string>
    </array>
    <key>KeepAlive</key>
    <true/>
</dict>
</plist>
EOF

# Set the correct permissions on the configuration and plist files
chown -R nobody:nogroup /usr/local/var/log/tinyproxy /usr/local/var/run/tinyproxy
chown root:wheel /Library/LaunchDaemons/com.tinyproxy.plist /usr/local/etc/tinyproxy/tinyproxy.conf
chmod 644 /Library/LaunchDaemons/com.tinyproxy.plist /usr/local/etc/tinyproxy/tinyproxy.conf

# Load the daemon
launchctl load /Library/LaunchDaemons/com.tinyproxy.plist

# Start the daemon
launchctl start com.tinyproxy
