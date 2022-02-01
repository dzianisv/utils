#!/bin/bash

for file in $*; do
    out=${file%.*}_story.jpg
    echo "Converting $file to $out"
    convert "$file" -resize 1920 -rotate 90 -crop 1080x1920+0 "$out" 
done
