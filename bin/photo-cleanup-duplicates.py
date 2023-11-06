#!/usr/bin/env python3

import os

# Create a dictionary to store the mapping of file names to their sizes and modification times
file_map = {}

print("Building files map")
# Iterate over all files in the current directory
for filename in os.listdir("."):
    if filename.endswith(".MP4"):
        # Get the size and modification time of the current file
        file_size = os.path.getsize(filename)
        file_modification_time = os.path.getmtime(filename)
        # Add the current file to the dictionary with its size and modification time
        file_map[filename] = (file_size, file_modification_time)

# Iterate over all pairs of files in the dictionary
for filename1, (file_size1, file_modification_time1) in file_map.items():
    if filename1.startswith("DJI_"):
        continue

    for filename2, (file_size2, file_modification_time2) in file_map.items():
        # If the files have the same size and modification time, they are considered duplicates
        if  filename1 != filename2 and file_size1 == file_size2 and file_modification_time1 == file_modification_time2:
           print(f"{filename1} duplicates {filename2}")
           os.rename(filename2, f".duplicated-{filename2}")
           