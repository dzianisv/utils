#!/bin/bash

for file in "$*"; do
    out=${file%.*}_story.jpg
    echo "Converting $file to $out"
    convert "$file" -rotate 90 -gravity South -crop 9:16 "$out" 
done
