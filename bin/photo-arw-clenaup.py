#!/usr/bin/env python3

import os
import sys
import argparse
from send2trash import send2trash


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("directory_arw", default=".", help='A workging directory with ARW files. By default set to the current working directory')
    parser.add_argument("directory_jpg", default=None, help='A reference directory with JPG files, optional, if not provided, set to <directory_arw> argument')
    args = parser.parse_args()

    # Set the directory where your ARW and JPG files are located
    directory_arw = args.directory_arw
    directory_jpg = args.directory_arw if args.directory_jpg is None else args.directory_jpg

    # Step 1: List all ARW files
    arw_files = set([file for file in os.listdir(directory_arw) if file.endswith(".ARW")])

    # Step 2: List all JPG files
    reference_files = set([file.replace('.JPG', '.ARW') for file in os.listdir(directory_jpg) if file.endswith(".JPG")])

    if len(arw_files) == 0:
        print("No JPG files in the JPG reference directory")
        return 1


    # Step 3: Remove ARW files to the macOS trash if a corresponding JPG file is not present
    for arw_file in arw_files:
        if arw_file not in reference_files:
            arw_path = os.path.join(directory_arw, arw_file)
            # Use send2trash to move the ARW file to the macOS trash
            send2trash(arw_path)
            print(f"Moved {arw_file} to macOS trash.")

if __name__ == "__main__":
    sys.exit(main())