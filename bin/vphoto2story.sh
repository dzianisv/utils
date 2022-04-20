#!/bin/bash
OUT=${OUT:-$(pwd)}

for file in $*; do
    output_path="$OUT/${file%.*}_story.jpg"
    echo "Converting $file to $output_path"
    convert "$file" -gravity center -crop 9:16 "$output_path" 
done
