#!/bin/bash

# Directory containing ARW files
ARW_DIR="."

# Output directory for DNG files
DNG_DIR="."

# Full path to Adobe DNG Converter
DNG_CONVERTER="/Applications/Adobe DNG Converter.app/Contents/MacOS/Adobe DNG Converter"

# Convert all ARW files to DNG
for file in "$ARW_DIR"/*.ARW; do
    "$DNG_CONVERTER" -c -d "$DNG_DIR" "$file"
done
