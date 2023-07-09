#!/bin/sh

# This script applies $LUT to all the RAW photos
# Usage: LUT=myStyle.cube ./photo-apply-lut.sh *.ARW
# It will apply lut and create .JPG file for each input RAW photo with the same name

LUT_INTENSITY=${LUT_INTENSITY:-0.75}

if ! command -v dcraw || ! command -v ffmpeg; then
    brew install dcraw ffmpeg
fi

for i in "$@"; do
    output=${i%.*}.jpg
    # In this command, -q:v 2 sets the quality of the output JPEG image. Lower values will give higher quality. The value of 2 corresponds roughly to a 90% quality setting in many other image processing tools.
    dcraw -c -w "$i" | ffmpeg -i - -filter_complex "[0:v]split[base][lut];[lut]lut3d='${LUT:?LUT is not set}'[lutout];[base][lutout]blend=all_expr='A*(1-$LUT_INTENSITY)+B*$LUT_INTENSITY'" -q:v 2 "${output}"
    touch -r "$i" "$output"
done

