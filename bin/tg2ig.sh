#!/bin/bash
set -eu

input="$1" # Replace with your actual input file name
output="${input%.*}-story.mp4" # Choose your desired output file name

# Get the original video dimensions
width=$(ffprobe -v error -select_streams v:0 -show_entries stream=width -of csv=p=0 "$input")
height=$(ffprobe -v error -select_streams v:0 -show_entries stream=height -of csv=p=0 "$input")


mask_image=circle_mask.png
# Create a circular mask with ImageMagick
convert -size ${width}x${height} xc:black -fill white -stroke black -draw "circle $(($width/2)),$(($height/2)) $(($width/2 - 1)),0" "$mask_image"
ffmpeg -i "$input" -i "$mask_image" -filter_complex "[0:v][1:v]scale2ref[video][mask];[mask]colorkey=white[ckout];[video][ckout]overlay" -c:a copy "$output"