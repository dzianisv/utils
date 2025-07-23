#!/bin/bash

# Script to restore file modification dates from JPG/MP4 metadata
# Usage: ./media-restore-mtime-from-metadata.sh file1 [file2 ...]

set -e

# Check if exiftool is installed
if ! command -v exiftool &> /dev/null; then
    echo "Error: exiftool is required but not installed."
    echo "Install with: brew install exiftool"
    exit 1
fi

processed=0
skipped=0
errors=0

# Function to restore date for a single file
restore_file_date() {
    local file="$1"
    local filename=$(basename "$file")
    
    echo "Processing: $filename"
    
    # Try different metadata fields for creation date
    # For JPG files: DateTimeOriginal, CreateDate, DateTime
    # For MP4 files: CreateDate, MediaCreateDate, TrackCreateDate
    
    local creation_date=""
    
    # Get file extension
    local ext="${file##*.}"
    ext=$(echo "$ext" | tr '[:upper:]' '[:lower:]')
    
    if [[ "$ext" == "jpg" || "$ext" == "jpeg" ]]; then
        # For JPEG files, try DateTimeOriginal first (EXIF), then CreateDate
        creation_date=$(exiftool -s -s -s -DateTimeOriginal "$file" 2>/dev/null || true)
        if [ -z "$creation_date" ]; then
            creation_date=$(exiftool -s -s -s -CreateDate "$file" 2>/dev/null || true)
        fi
        if [ -z "$creation_date" ]; then
            creation_date=$(exiftool -s -s -s -DateTime "$file" 2>/dev/null || true)
        fi
    elif [[ "$ext" == "mp4" || "$ext" == "mov" ]]; then
        # For MP4/MOV files, try CreateDate first, then MediaCreateDate
        creation_date=$(exiftool -s -s -s -CreateDate "$file" 2>/dev/null || true)
        if [ -z "$creation_date" ]; then
            creation_date=$(exiftool -s -s -s -MediaCreateDate "$file" 2>/dev/null || true)
        fi
        if [ -z "$creation_date" ]; then
            creation_date=$(exiftool -s -s -s -TrackCreateDate "$file" 2>/dev/null || true)
        fi
    fi
    
    if [ -n "$creation_date" ] && [ "$creation_date" != "-" ] && [ "$creation_date" != "0000:00:00 00:00:00" ]; then
        # Convert the date format to what touch expects
        # Input format: "2023:12:25 14:30:45" or "2023-12-25T14:30:45"
        # Output format for touch: "202312251430.45"
        
        # Handle different date formats
        if [[ "$creation_date" =~ ^[0-9]{4}:[0-9]{2}:[0-9]{2}\ [0-9]{2}:[0-9]{2}:[0-9]{2}$ ]]; then
            # Format: "2023:12:25 14:30:45"
            # Convert to "202312251430.45"
            temp_date=$(echo "$creation_date" | sed 's/://g' | sed 's/ //g')
            touch_date="${temp_date:0:12}.${temp_date:12:2}"
        elif [[ "$creation_date" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2} ]]; then
            # Format: "2023-12-25T14:30:45"
            # Convert to "202312251430.45"
            temp_date=$(echo "$creation_date" | sed 's/-//g' | sed 's/T//' | sed 's/://g')
            touch_date="${temp_date:0:12}.${temp_date:12:2}"
        else
            echo "  ⚠️  Unknown date format: $creation_date"
            errors=$((errors + 1))
            return
        fi
        
        # Set the modification time
        if touch -t "$touch_date" "$file" 2>/dev/null; then
            echo "  ✅ Updated: $creation_date"
            processed=$((processed + 1))
        else
            echo "  ❌ Failed to set date: $creation_date (touch format: $touch_date)"
            errors=$((errors + 1))
        fi
    else
        echo "  ⚠️  No creation date found in metadata"
        skipped=$((skipped + 1))
    fi
}

# Process provided JPG and MP4 files
for file in "$@"; do
    restore_file_date "$file"
done

# Print summary
echo
echo "Summary:"
echo "  Processed: $processed"
echo "  Skipped: $skipped"
echo "  Errors: $errors"

# Exit with appropriate code
if [ $errors -gt 0 ]; then
    exit 1
else
    exit 0
fi
