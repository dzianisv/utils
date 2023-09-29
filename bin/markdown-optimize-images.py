#!/usr/bin/env python3

"""
processes markdown files, moving images to a unified "img" folder, converts PNG and JPG images to WEBP format for optimization, and updates markdown image references accordingly
"""

import os
import re
import logging
import sys
import subprocess
import uuid

logger = logging.getLogger(__file__)
logger.setLevel(logging.DEBUG)
logger.addHandler(logging.StreamHandler(sys.stderr))

img_folder ='img'

def optimize_image(png_path, quality=70):
    output_path = os.path.join(os.path.dirname(png_path), f"{uuid.uuid4()}.webp")
    cmd = ["convert", png_path, "-quality", str(quality), output_path]
    subprocess.check_call(cmd)
    return output_path

def unify_images(image_path, ):
    _name, ext = os.path.splitext(image_path)

    if not os.path.exists(img_folder):
        os.makedirs(img_folder)

    new_path = os.path.join(img_folder, f"{uuid.uuid4()}{ext}")
    subprocess.run(["git", "mv", image_path, new_path])
    return new_path

def cleanup_markdown(file_path):
    with open(file_path, 'r') as file:
        content = file.read()

    image_regex =  r'!\[.*\]\(((?!http)(?!https).+\.(png|jpg|webp))\)'
    logger.info("processing \"%s\"", file_path)
    image_tags = re.findall(image_regex, content)
    for image_tag in image_tags:
        logger.debug("processing tag %s", image_tag)
        image_uri, image_ext = image_tag

        path = os.path.join(os.path.dirname(file_path), image_uri)
        logger.debug('found an image "%s"', path)
        if os.path.exists(path):  # checks if the png file exists
            new_path = None

            # move the image to the img folder if it is not already there
            absolute_path = os.path.realpath(os.path.join(os.path.dirname(file_path), image_uri))
            img_dir = os.path.realpath(img_folder)

            if not absolute_path.startswith(img_dir):
                new_path = unify_images(path)

            # convert only png and jpg images
            if image_ext in set(['png', 'jpg']):
                new_path = optimize_image(path if new_path is None else new_path)

                try:
                    os.remove(path)
                    logger.debug('removed "%s"', path)
                except (OSError, PermissionError) as e:
                    logger.error(f"Error: Unable to remove file {path}: %s", e)

            if new_path is None:
                continue

            # replace the image uri with the new relative image path
            content = content.replace(image_uri, os.path.relpath(new_path, os.path.dirname(file_path)))

    with open(file_path, 'w') as file:
        file.write(content)

def find_and_replace_in_md_files():
    for root, _, files in os.walk('.'):
        for file in files:
            if file.endswith('.md'):
                file_path = os.path.join(root, file)
                cleanup_markdown(file_path)

if __name__ == '__main__':
    find_and_replace_in_md_files()
