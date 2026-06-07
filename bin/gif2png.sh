#!/bin/bash

# Convert GIF to PNG frames
# Usage: gif2png.sh <input.gif> [output_prefix]

set -e

if [ $# -lt 1 ]; then
    echo "Usage: $(basename "$0") <input.gif> [output_prefix]"
    echo "  input.gif      - Input GIF file"
    echo "  output_prefix  - Output filename prefix (default: input filename without extension)"
    exit 1
fi

INPUT="$1"

if [ ! -f "$INPUT" ]; then
    echo "Error: File '$INPUT' not found"
    exit 1
fi

if [ -n "$2" ]; then
    PREFIX="$2"
else
    PREFIX="${INPUT%.*}"
fi

if ! command -v convert &> /dev/null; then
    echo "Error: ImageMagick is not installed"
    echo "Install with: brew install imagemagick"
    exit 1
fi

echo "Converting '$INPUT' to PNG frames..."
convert "$INPUT" -coalesce "${PREFIX}_%03d.png"

COUNT=$(ls -1 "${PREFIX}"_*.png 2>/dev/null | wc -l | tr -d ' ')
echo "Done! Created $COUNT frame(s): ${PREFIX}_000.png ..."
