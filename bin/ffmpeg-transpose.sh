#!/bin/bash

set -e

for input in "$@"; do
    if [[ ! -f "$input" ]]; then
        echo "❌ File not found: $input"
        continue
    fi

    dir=$(dirname "$input")
    base=$(basename "$input")
    name="${base%.*}"
    ext="${base##*.}"
    output="${dir}/${name}-90.${ext}"

    echo "➡️ Rotating: $input → $output"

    ffmpeg -i "$input" -vf "transpose=2" -c:v libx264 -crf 23 -preset fast -c:a aac "$output"

    if [[ $? -eq 0 && -f "$output" ]]; then
        # Preserve original modification time
        orig_mtime=$(stat -f "%Sm" -t "%Y%m%d%H%M.%S" "$input")
        touch -t "$orig_mtime" "$output"

        # Delete original
        echo "🗑️ Deleting original: $input"
        rm "$input"
    else
        echo "❗ Failed to convert: $input"
    fi
done

echo "✅ Done."


