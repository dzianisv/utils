#!/usr/bin/env python3

import os
import sys
from send2trash import send2trash

# Set the directory where your ARW and JPG files are located
directory = sys.argv[1]

# Step 1: List all ARW files
arw_files = [file for file in os.listdir(directory) if file.endswith(".ARW")]

# Step 2: List all JPG files
jpg_files = [file for file in os.listdir(directory) if file.endswith(".JPG")]

# Step 3: Remove ARW files to the macOS trash if a corresponding JPG file is not present
for arw_file in arw_files:
    jpg_file = arw_file.replace(".ARW", ".JPG")
    if jpg_file not in jpg_files:
        arw_path = os.path.join(directory, arw_file)

        # Use send2trash to move the ARW file to the macOS trash
        send2trash(arw_path)
        print(f"Moved {arw_file} to macOS trash.")
