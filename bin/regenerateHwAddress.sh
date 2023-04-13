#!/bin/sh
NIF=en0
MAC_ADDRESS=$(echo 00:60:2f$(hexdump -n3 -e '/1 ":%02X"' /dev/random))
ifconfig "$NIF" down
ifconfig "$NIF" up
ifconfig "$NIF" ether ${MAC_ADDRESS}
