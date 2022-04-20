#!/bin/bash

for file in "$*"; do
    out=${file%.*}_story.jpg
    echo "Converting $file to $out"
    w=$(identify -format '%w' "$file")
    h=$(identify -format '%h' "$file")
    if (( w < h)); then
        ARGS="-rotate 90 -crop 9:16"
    else
        ARGS="-crop 16:9"
    fi
    convert "$file" -gravity Center $ARGS "$out" 
done
