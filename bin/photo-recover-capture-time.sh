#!/bin/bash
# This script set a modification time of the file to the capture time
# The capture time is gotten from the exif metadata of the photo file
# Usage: ./photo-recover-capture-time.sh *.dng

# Function to convert EXIF date format to a format touch understands
function date_format {
    echo "$1" | sed -E 's/([0-9]{4}):([0-9]{2}):([0-9]{2}) ([0-9]{2}):([0-9]{2}):([0-9]{2})/\1\2\3\4\5.\6/'
}

for file in "$@"; do
    # Extract the capture date
    DATE=$(exiftool -s -s -s -DateTimeOriginal "$file")

    # Convert the date to a format touch understands
    NEW_DATE=$(date_format "$DATE")

    # Update the file's modification time
    echo "$file $NEW_DATE"
    touch -t "$NEW_DATE" "$file"
done
