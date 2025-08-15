#!/bin/bash
set -euo pipefail

rootfs=${1:-/mnt/}
mount --rbind /dev $rootfs/dev || :
mount --rbind /sys $rootfs/sys || :
mount -t proc none $rootfs/proc  || :
mount --rbind /run $rootfs/run
mount --rbind /run/systemd/resolve/stub-resolv.conf  $rootfs/etc/resolv.conf 
exec chroot $rootfs bash