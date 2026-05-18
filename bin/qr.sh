#!/bin/bash

COLOR="white"
SIZE=1024
TEXT=""

# Parse arguments
while [[ $# -gt 0 ]]; do
  case $1 in
    --black)
      COLOR="black"
      shift
      ;;
    --white)
      COLOR="white"
      shift
      ;;
    *)
      TEXT="$1"
      shift
      ;;
  esac
done

if [ -z "$TEXT" ]; then
  echo "Usage: ./qr.sh [--black|--white] \"https://example.com\""
  exit 1
fi

# Generate QR code as PNG
qrencode -t PNG -o qr_temp.png -s 10 "$TEXT"

# Convert to specified color QR on transparent background
if [ "$COLOR" = "white" ]; then
  magick qr_temp.png \
    -alpha set \
    -channel RGBA \
    -fuzz 1% -fill none -opaque white \
    -fill white -opaque black \
    -resize ${SIZE}x${SIZE} \
    PNG32:qr.png
else
  magick qr_temp.png \
    -alpha set \
    -channel RGBA \
    -fuzz 1% -fill none -opaque white \
    -resize ${SIZE}x${SIZE} \
    PNG32:qr.png
fi

rm qr_temp.png

echo "✅ QR code generated: qr.png ($COLOR)"