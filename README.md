This repository contains a collection of useful bash scripts that can be used to configure various operating systems and developer machines. The scripts have been tested on the following systems: Ubuntu, Armbian, OpenWrt, macOS. Please note that some scripts may require administrative privileges to run.

## Flash Armbian and setup Avahi Daemon for local network discovery
The most anoying thing for me is to discover Armbian computer IP for inital `ssh` to config the OS.
Usually I go to the router webconsole to see DHCP leases and this is very anoying. I created
```sh
armbian-flash.sh ~/Downloads/armbin.img.xz /dev/sdb
```
script to flash the image and then install Avahi daemon, so you will discover your Arm host in the network using mDNS, for instance using `bananapi.local` mDNS name.

## Chroot into Arm-based Linux
You can simply insert a RaspberryPi, BananaPi or OrangePi flash into your Linux machine and chroot into the embedded Linux rootfs using `bin/chroot-arm`.

```sh
bin/chroot-arm /media/$USER/sdcard
```

## Configure VPN servers
This script configures a Wireguard server and generate configurations for the clients

```sh
curl "https://raw.githubusercontent.com/dzianisv/utils/master/bin/linux-configure-wireguard.sh" | N=10 bash -x
```

Or configure PPTP server on the Linux host:
```sh
```sh
curl "https://raw.githubusercontent.com/dzianisv/utils/master/bin/linux-configure-pptp-server.sh" | bash -x
```
```


