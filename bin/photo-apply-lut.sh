#!/bin/sh

# This script applies $LUT to all the RAW photos
# Usage: LUT=myStyle.cube ./photo-apply-lut.sh *.ARW
# It will apply lut and create .JPG file for each input RAW photo with the same name

LUT_INTENSITY=${LUT_INTENSITY:-0.75}

if ! command -v dcraw || ! command -v ffmpeg; then
    brew install dcraw ffmpeg
fi

for i in $*; do
    output=${i%.*}.jpg
    dcraw -c -w "$i" | ffmpeg -i - -filter_complex "[0:v]split[base][lut];[lut]lut3d='$LUT'[lutout];[base][lutout]blend=all_expr='A*(1-$LUT_INTENSITY)+B*$LUT_INTENSITY'" "${output}"
done

