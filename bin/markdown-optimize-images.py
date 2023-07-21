#!/usr/bin/env python3

import os
import re
import logging
import sys
import subprocess


logger = logging.getLogger(__file__)
logger.setLevel(logging.DEBUG)
logger.addHandler(logging.StreamHandler(sys.stderr))

def optimize_image(png_path, quality=70):
    output_path = re.sub(r'\.(png|jpg)$', '.webp', png_path)
    cmd = ["convert", png_path, "-quality", str(quality), output_path]
    subprocess.check_call(cmd)
    return output_path

def replace_png_with_jpg(file_path):
    with open(file_path, 'r') as file:
        content = file.read()

    image_regex =  r'!\[.*\]\(((?!http)(?!https).+\.(png|jpg))\)'
    logger.info("processing \"%s\"", file_path)
    image_tags = re.findall(image_regex, content)
    for image_tag in image_tags:
        logger.debug("processing tag %s", image_tag)
        image_uri, image_ext = image_tag
        path = os.path.join(os.path.dirname(file_path), image_uri)
        logger.debug('found image path "%s"', path)
        if os.path.exists(path):  # checks if the png file exists
            new_path = optimize_image(path)
            if new_path is None:
                continue

            try:
                os.remove(path)
                logger.debug('removed "%s"', path)
            except (OSError, PermissionError) as e:
                logger.error(f"Error: Unable to remove file {path}: %s", e)

            content = content.replace(image_uri, image_uri.replace('.' + image_ext, '.webp'))

    with open(file_path, 'w') as file:
        file.write(content)

def find_and_replace_in_md_files():
    for root, _, files in os.walk('.'):
        for file in files:
            if file.endswith('.md'):
                file_path = os.path.join(root, file)
                replace_png_with_jpg(file_path)

if __name__ == '__main__':
    find_and_replace_in_md_files()
