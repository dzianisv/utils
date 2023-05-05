#!/usr/bin/env python3
import os
import re

def replace_png_with_jpg(file_path):
    with open(file_path, 'r') as file:
        content = file.read()
    content = re.sub(r'!\[.*\]\((?!http)(?!https).*\.png\)', lambda m: m.group(0).replace('.png', '.jpg'), content)
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
