#!/bin/bash
MP3="$1"

# Get the base name without extension
BASENAME="${MP3%.mp3}"
OUTPUT="${BASENAME}.mp4"

# Get duration of the MP3 file
DURATION=$(ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 "$MP3")

ffmpeg -y -i "$MP3" -map 0:v -c:v copy cover.jpg
ffmpeg -y -loop 1 -i cover.jpg -i "$MP3" -c:v libx264 -tune stillimage -c:a aac -b:a 192k -pix_fmt yuv420p \
-filter_complex "[0:v]scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2[scaled]; \
[1:a]showfreqs=s=800x150:mode=line:fscale=log:colors=white:cmode=separate[freq]; \
[scaled][freq]overlay=x=(W-w)/2:y=(H-h)/2:format=auto[withfreq]; \
color=c=white:s=1080x30[bar]; \
[withfreq][bar]overlay=W*t/${DURATION}-W:H-h:shortest=1[out]" \
-map "[out]" -map 1:a -shortest "$OUTPUT"
rm cover.jpg
