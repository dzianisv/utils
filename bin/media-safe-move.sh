#!/bin/bash

# Safe script to move JPG files with conflict resolution
# Usage: ./safe_move_jpg.sh

DEST_DIR="/Volumes/Dzianis-2/LifeHistory/"

# Check if destination directory exists
if [ ! -d "$DEST_DIR" ]; then
    echo "Error: Destination directory '$DEST_DIR' does not exist."
    exit 1
fi

# Counter for processed files
processed=0
duplicates_removed=0
conflicts_renamed=0

# Find all JPG files (case insensitive)
find . -iname '*.3gp' -o -iname '*.360' -o -iname '*.JPG' -o -iname '*.MP4'  -o -iname '*.HEIC' -o -iname '*.ARW' | while read -r source_file; do
    # Get just the filename without path
    filename=$(basename "$source_file")
    dest_file="$DEST_DIR$filename"
    
    echo "Processing: $source_file"
    
    # Check if destination file already exists
    if [ -f "$dest_file" ]; then
        echo "  File exists in destination, comparing..."
        
        # Compare files byte by byte
        if cmp -s "$source_file" "$dest_file"; then
            echo "  Files are identical - removing source file"
            rm "$source_file"
            ((duplicates_removed++))
        else
            echo "  Files are different - finding unique name"
            
            # Find a unique filename by adding counter
            counter=1
            name_without_ext="${filename%.*}"
            extension="${filename##*.}"
            
            while [ -f "$DEST_DIR${name_without_ext}-${counter}.${extension}" ]; do
                ((counter++))
            done
            
            new_dest_file="$DEST_DIR${name_without_ext}-${counter}.${extension}"
            echo "  Moving to: ${name_without_ext}-${counter}.${extension}"
            
            # Get modification time before moving
            mod_time=$(stat -f "%Sm" -t "%Y%m%d%H%M.%S" "$source_file")
            mv "$source_file" "$new_dest_file"
            # Restore modification time after moving
            touch -t "$mod_time" "$new_dest_file"
            ((conflicts_renamed++))
        fi
    else
        echo "  Moving to destination (no conflict)"
        # Get modification time before moving
        mod_time=$(stat -f "%Sm" -t "%Y%m%d%H%M.%S" "$source_file")
        mv "$source_file" "$dest_file"
        # Restore modification time after moving
        touch -t "$mod_time" "$dest_file"
    fi
    
    ((processed++))
done

echo ""
echo "=== Summary ==="
echo "Total files processed: $processed"
echo "Duplicate files removed: $duplicates_removed"
echo "Files renamed due to conflicts: $conflicts_renamed"
echo "Files moved without conflict: $((processed - duplicates_removed - conflicts_renamed))"
