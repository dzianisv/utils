#!/bin/sh

# This script creates a .CUBE LUT previews from image $SRC
# Usage ./photo-preview-lut.sh *.cube
# It will create file .jpg preview for each .CUBE file

LUT_INTENSITY=1.0

if ! command -v dcraw || ! command -v ffmpeg; then
    brew install dcraw ffmpeg
fi

for LUT in $*; do
    for i in $SRC; do
        output=${LUT%.*}.jpg
        dcraw -c -w "$i" | ffmpeg -i - -filter_complex "[0:v]split[base][lut];[lut]lut3d='$LUT'[lutout];[base][lutout]blend=all_expr='A*(1-$LUT_INTENSITY)+B*$LUT_INTENSITY'" "${output}"
    done
done

