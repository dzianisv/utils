#!/bin/bash
set -xeo pipefail

if [ ! -f /swapfile ]; then
    fallocate -l 16G /swapfile
    chmod 600 /swapfile
    mkswap /swapfile
    swapon /swapfile
    echo '/swapfile swap swap defaults 0 0' >> /etc/fstab
fi


UUID=$(findmnt -no UUID -T /swapfile)
OFFSET=$(filefrag -v /swapfile | awk '{ if($1=="0:"){print substr($4, 1, length($4)-2)} }')

echo "RESUME=UUID=$UUID resume_offset=$OFFSET" > /etc/initramfs-tools/conf.d/resume.conf
sed -i "s/resume=[^ ]//g" /etc/default/grub
sed -i "s/resume_offset=[^ ]//g" /etc/default/grub
sed -i "s/GRUB_CMDLINE_LINUX_DEFAULT=\"[^\"]*/& resume=UUID=$UUID resume_offset=$OFFSET\/" /etc/default/grub


update-grub
update-initramfs -u -k all
