#!/bin/sh

set -eu

for f in "$@"; do
    name=${f%.*}
    heif-convert -q 95 "${f}" "${name}.jpg"
done