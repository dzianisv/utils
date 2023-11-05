#!/bin/bash

# This script keeps the renamed DJI files
# And removes the DJI_ prefixed duplicates
# I wrote it to clean up the media folder from duplicates

get_size() {
    stat -c%s "$1"
}

for f in *.MP4; do
    if [[ "$f" =~ DJI_* ]]; then
        continue
    fi

    f_size=$(get_size "$f")

    for f2 in *.MP4; do
        if [[ "$f" != "$f2" ]] && [[ "$f_size" -eq "$(get_size "$f2")" ]] && cmp "$f" "$f2"; then
            touch -r "$f2" "$f" # restore a modication time
            mv "$f2" ".trashed-$f2"
        fi
    done
done
