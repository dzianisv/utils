#!/bin/bash

echo "g_serial" >> etc/modules
echo "ttyGS0" >> etc/securetty
mkdir -p etc/systemd/system/serial-getty@ttyGS0.service.d

cat > etc/systemd/system/serial-getty@ttyGS0.service.d/10-switch-role.conf <<EOL
[Service]
ExecStartPre=-/bin/sh -c "echo 2 > /sys/bus/platform/devices/sunxi_usb_udc/otg_role"
EOL

ln -s lib/systemd/system/serial-getty@.service etc/systemd/system/getty.target.wants/serial-getty@ttyGS0.service
