#!/bin/sh

# This script creates a .CUBE LUT previews from image $SRC
# Usage ./photo-preview-lut.sh *.cube
# It will create file .jpg preview for each .CUBE file

if ! command -v dcraw || ! command -v ffmpeg; then
    brew install dcraw ffmpeg
fi

for LUT in "$@"; do
    for i in $SRC; do
        output=${LUT%.*}.jpg
        dcraw -c -w "$i" | ffmpeg -i - -vf lut3d="$LUT" "${output}"
    done
done

