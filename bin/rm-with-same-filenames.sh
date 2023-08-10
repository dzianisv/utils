#!/bin/bash

# Define directories
DIR1=${1:?reference dir is not set}
DIR2=${2:?dir to clean is not set}

# Enable case-insensitive matching
shopt -s nocaseglob

# Iterate over files in DIR2
for file in "$DIR2"/*; do
    # If the file also exists in DIR1 (ignoring case), remove it from DIR2
    if [ -e "$DIR1"/$(basename "$file") ]; then
        echo "Removing file $file from $DIR2"
        rm "$file"
    fi
done

# Disable case-insensitive matching
shopt -u nocaseglob