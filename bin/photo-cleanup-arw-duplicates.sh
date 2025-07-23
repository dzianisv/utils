#!/usr/bin/env bash
# move_raw_duplicates.sh
# Usage:  ./move_raw_duplicates.sh  [PHOTO_ROOT]
#         PHOTO_ROOT defaults to the current directory (.)
#         A RAW/ directory will be created alongside it if necessary.

set -euo pipefail

PHOTO_ROOT="${1:-.}"            # Where your photos live
RAW_ROOT="$PHOTO_ROOT/RAW"       # Where matching .ARW files will be placed
mkdir -p "$RAW_ROOT"

# Find every JPG/JPEG (case‑insensitive), even in sub‑folders
find "$PHOTO_ROOT" -type f \( -iname '*.jpg' -o -iname '*.jpeg' \) | while IFS= read -r jpg_path; do
    # Remove the extension to get the stem (…/IMG_1234)
    stem="${jpg_path%.*}"

    # Look for the matching ARW (handle either .ARW or .arw on case‑sensitive filesystems)
    for ext in ARW arw; do
        raw_path="${stem}.${ext}"
        [[ -e "$raw_path" ]] || continue   # No RAW file; skip

        # Build the destination path inside RAW/, preserving sub‑folders
        rel_path="${raw_path#"$PHOTO_ROOT"/}"            # path relative to root
        dest_path="$RAW_ROOT/$rel_path"

        mkdir -p "$(dirname "$dest_path")"                # recreate sub‑folder(s)
        mv -v "$raw_path" "$dest_path"                    # move with a progress line
        break                                             # don’t check the second ext
    done
done
