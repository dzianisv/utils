#!/bin/sh

LUT_INTENSITY=0.25

if ! command -v dcraw || ! command -v ffmpeg; then
    brew install dcraw ffmpeg
fi

for i in $*; do
    output=${i%.*}.jpg
    dcraw -c -w "$i" | ffmpeg -i - -filter_complex "[0:v]split[base][lut];[lut]lut3d='$LUT'[lutout];[base][lutout]blend=all_expr='A*(1-$LUT_INTENSITY)+B*$LUT_INTENSITY'" "${output}"
done

