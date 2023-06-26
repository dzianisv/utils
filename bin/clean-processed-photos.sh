#!/bin/bash

raw_photos=(*.ARW)

for raw_photo in "${raw_photos[@]}"; do
    for ext in jpg JPG jpeg JPEG; do
        jpg_file="${raw_photo%.*}.${ext}"
        if [[ -f "$jpg_file" ]]; then
            arw_mod_time=$(stat -f %m "$raw_photo")
            jpg_mod_time=$(stat -f %m "$jpg_file")

            if (( jpg_mod_time - arw_mod_time > 30 )); then
                echo "Removing $raw_photo"
                mv "$raw_photo" ".trashed-$raw_photo"
            fi
        fi
    done
done
