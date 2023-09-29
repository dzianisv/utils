#!/usr/bin/env python3

"""
identifies and removes unused images referenced in markdown files within a directory
"""

import os
import re
import uuid
import subprocess
import logging


logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
logger.addHandler(logging.StreamHandler())

def find_md_files(directory="."):
    """Find all .md files recursively in the given directory."""
    for root, _, files in os.walk(directory):
        for file in files:
            if file.endswith(".md"):
                yield os.path.join(root, file)

def extract_image_paths_from_md(md_file):
    """Extract image paths from a markdown file and return paths relative to the current directory."""
    with open(md_file, 'r') as file:
        content = file.read()
        img_paths = re.findall(r'!\[.*?\]\((.*?)\)', content)
        # Normalize paths to be relative to the current directory
        normalized_paths = [os.path.normpath(os.path.join(os.path.dirname(md_file), path)) for path in img_paths]
        return normalized_paths


def find_images(directory="."):
    """Find all images with extensions [png, jpg, webp] recursively in the given directory."""
    extensions = ['.png', '.jpg', '.webp']
    for root, _, files in os.walk(directory):
        for file in files:
            if any(file.endswith(ext) for ext in extensions):
                yield os.path.join(root, file)[2:] if root.startswith("./") else os.path.join(root, file)
def main():
    # Step 1 and 2: Find all .md files and extract image paths
    referenced_images = set()
    for md_file in find_md_files():
        referenced_images.update(extract_image_paths_from_md(md_file))

    # Step 3: Build a set of the relative image paths
    # (This is already done in the above step)

    # Step 4: Find all images
    all_images = set(find_images())

    logger.info("Referenced images: %s", referenced_images)
    logger.info("All images: %s", all_images)
    logger.info("Unused images: %s", all_images - referenced_images)

    # Remove all the unused images
    unused_images = all_images - referenced_images
    for img in unused_images:
        logger.info("Removing %s: %d", img, img in referenced_images)
        os.remove(img)

if __name__ == "__main__":
    main()
