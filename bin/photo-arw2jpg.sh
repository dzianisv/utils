#!/bin/sh

find . -type f \( -iname "*.ARW" -o -iname "*.RAW" \) -exec sh -c 'darktable-cli {} ${0%.*}.jpeg' {} \;