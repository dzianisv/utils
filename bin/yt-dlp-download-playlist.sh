#!/bin/bash
playlist=$(< playlist.txt)
for i in $playlist; do
    yt-dlp -x --audio-format=mp3 "$i"
done