#!/bin/sh
#
# extroot_usb.sh
# Automate OpenWrt extroot setup onto a USB flash drive
# Usage: ./extroot_usb.sh /dev/sdX1
#

set -e

if [ "$(id -u)" -ne 0 ]; then
  echo "Error: must be run as root"
  exit 1
fi

DEV="$1"
MNT="/mnt/usb"

# 1. Install prerequisites
opkg update                                                       # :contentReference[oaicite:0]{index=0}
opkg install block-mount kmod-usb-storage kmod-fs-ext4 e2fsprogs    # :contentReference[oaicite:1]{index=1}
opkg install usbutils                                              # optional, for lsblk etc :contentReference[oaicite:2]{index=2}

# 2. Format the USB partition as ext4 with label extroot
echo "Formatting ${DEV} as ext4 (label: extroot)..."
mkfs.ext4 -L extroot "${DEV}"                                      # :contentReference[oaicite:3]{index=3}

# 3. Mount USB and copy existing overlay data
echo "Mounting ${DEV} to ${MNT}..."
mkdir -p "${MNT}"
mount "${DEV}" "${MNT}"                                            # :contentReference[oaicite:4]{index=4}
echo "Copying current overlay (/overlay) to USB..."
tar -C /overlay -cf - . | tar -C "${MNT}" -xf -                  # :contentReference[oaicite:5]{index=5}

# 4. Configure extroot in /etc/config/fstab
echo "Configuring extroot in /etc/config/fstab..."
block detect > /etc/config/fstab                                   # :contentReference[oaicite:6]{index=6}
# Replace first fstab mount to overlay on USB
uci set fstab.@mount[0].target='/overlay'
uci set fstab.@mount[0].device=LABEL=extroot
uci set fstab.@mount[0].fstype='ext4'
uci set fstab.@mount[0].options='rw,sync'
uci set fstab.@mount[0].enabled='1'
uci commit fstab
/etc/init.d/fstab enable                                           # :contentReference[oaicite:7]{index=7}

# 5. Cleanup and reboot
umount "${MNT}"
echo "Extroot setup complete—rebooting now..."


