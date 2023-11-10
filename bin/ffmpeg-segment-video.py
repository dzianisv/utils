#!/usr/bin/env python3
import sys
import re
import subprocess

# Function to convert time format to seconds
def time_to_seconds(time_str):
    hours, minutes, seconds, milliseconds = map(int, time_str.split('.'))
    return hours * 3600 + minutes * 60 + seconds + milliseconds / 1000

def extract_timestamps_and_generate_ffmpeg_command(file_name):
    # Regular expression to extract timestamps
    timestamp_pattern = r"(\d{2}\.\d{2}\.\d{2}\.\d{3})-(\d{2}\.\d{2}\.\d{2}\.\d{3})"

    # Extract timestamps
    match = re.search(timestamp_pattern, file_name)
    if match:
        offset_str, duration_str = match.groups()

        # Convert to seconds
        offset_seconds = time_to_seconds(offset_str)
        duration_seconds = time_to_seconds(duration_str) - offset_seconds

        # Generate the ffmpeg command
        return f"ffmpeg -i \"$ORIGINAL_VIDEO\" -ss {offset_seconds} -t {duration_seconds} -c:v h264 -c:a aac -crf 25 \"{file_name[:-5]}.mp4\""
    else:
        return f"No timestamps found in the file name: {file_name}"

# Main function to iterate over command line arguments
def main():
    for file_name in sys.argv[1:]:
        ffmpeg_command = extract_timestamps_and_generate_ffmpeg_command(file_name)
        subprocess.run(ffmpeg_command, shell=True)

# Example usage: python script.py file1.webm file2.webm
if __name__ == "__main__":
    main()
