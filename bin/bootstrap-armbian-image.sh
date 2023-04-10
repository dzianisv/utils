#!/bin/bash
set -euxo pipefail

shell() {
    chroot . /usr/bin/qemu-arm-static /bin/sh -c "$*"
}


image=$1
disk=/dev/sdb
model=$(lsblk -o model $disk | tail -n2)
vendor=$(lsblk -o vendor $disk | tail -n2)
echo "Writing image to $vendor $model $disk"

# xz -d -c < "$image" | dd bs=4096 "of=$disk" status=progress
partprobe "$disk"
mountpoint=$(n -o TARGET --first-only "$disk" || : )
if [ -z "$mountpoint" ]; then
    workdir=$(mktemp -d)
    # trap "rm -rf $workdir" EXIT
    cd "$workdir"
    mkdir -p rootfs
    mount  -o rw "${disk}1" rootfs
    trap "umount ${disk}1" EXIT
    cd rootfs
else
    cd "$mountpoint"
fi

install -m 0755 `command -v qemu-arm-static` usr/bin/qemu-arm-static
mount -t devtmpfs none dev
trap "umount dev" EXIT
mount -t proc none proc
trap "umount proc" EXIT
mount -t sysfs none sys
trap "umount sys" EXIT

shell "apt update -yq && apt install -yq avahi-daemon"
curl "https://raw.githubusercontent.com/lathiat/avahi/master/avahi-daemon/ssh.service" > etc/avahi/services/ssh.service
