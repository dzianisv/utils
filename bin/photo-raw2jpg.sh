#!/bin/bash

for i in "$@"; do
    dcraw -c -w "$i" | magick convert - "${i%.*}.jpg"
done
