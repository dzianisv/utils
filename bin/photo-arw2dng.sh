#!/bin/bash

set -eu

# Output directory for DNG files
out_dir="."

# Full path to Adobe DNG Converter
DNG_CONVERTER="/Applications/Adobe DNG Converter.app/Contents/MacOS/Adobe DNG Converter"

# Convert all ARW files to DNG
for file in "$@"; do
    in_name=$(basename "$file")
    out_name=${in_name%.*}.dng

    "$DNG_CONVERTER" -c -d "$out_dir" "$file"
    touch -r "$file" "$out_dir/$out_name"
done
