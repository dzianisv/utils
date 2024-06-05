#!/bin/bash
set -eu

# Check if an input file was provided
if [ -z "$1" ]; then
  echo "Usage: $0 <input_video_file>"
  exit 1
fi

# Check if the input file exists
if [ ! -f "$1" ]; then
  echo "Error: File '$1' not found."
  exit 1
fi

# Get the input video file from the first argument
input_video="$1"

# Extract filename without the extension and the file extension
filename=$(basename -- "$input_video")
extension="${filename##*.}"
filename="${filename%.*}"

# Create the output video filename by adding -story before the file extension
output_video="${filename}-story.${extension}"
canvas="$(dirname $0)/../share/canvas.png"

canvas_resolution=$(ffprobe -v error -select_streams v:0 -show_entries stream=width,height -of csv=p=0 "$canvas")

# Run FFmpeg to scale the input video to the canvas size and overlay it on the canvas
ffmpeg -i "$input_video" -i "$canvas" -filter_complex \
"[1:v]scale=$canvas_resolution[canvas]; \
 [0:v]scale=$canvas_resolution:force_original_aspect_ratio=decrease,pad=$canvas_resolution:(ow-iw)/2:(oh-ih)/2[video]; \
 [canvas][video]overlay=shortest=1" \
-c:v libx264 -c:a aac -strict experimental "$output_video"