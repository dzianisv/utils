#!/bin/bash

TEXT="$1"
OUT="qr.png"
SIZE=1024

if [ -z "$TEXT" ]; then
  echo "Usage: ./qr.sh \"https://example.com\""
  exit 1
fi

# Generate transparent SVG
qrencode -t SVG -o qr.svg "$TEXT"

# Convert to white QR on transparent background PNG
convert qr.svg \
  -background none \
  -fill white \
  -colorize 100 \
  -resize ${SIZE}x${SIZE} \
  qr.png

rm qr.svg

echo "✅ QR code generated: qr.png"