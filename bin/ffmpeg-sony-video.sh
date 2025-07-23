#!/bin/bash

# Check if at least one file is provided
if [ "$#" -lt 1 ]; then
    echo "Usage: $0 <video_file1> <video_file2> ... <video_fileN>"
    exit 1
fi

# Iterate over all input files
for input_file in "$@"; do
    # Extract the directory, filename, and extension
    dir=$(dirname "$input_file")
    base_name=$(basename "$input_file")
    extension="${base_name##*.}"
    filename="${base_name%.*}"

    # Construct the output file name with the prefix
    output_file="${dir}/${filename}.aac.${extension}"

    # Run ffmpeg to convert the audio codec to AAC with 192 kbps
    ffmpeg -i "$input_file" -c:v copy -c:a aac -b:a 192k "$output_file"

    # Check if the command was successful
    if [ $? -eq 0 ]; then
        echo "Converted: $input_file -> $output_file"
    else
        echo "Error converting: $input_file"
    fi
done