#!/usr/bin/env python3
import sys

def txt_to_md(txt_file, md_file):
    lines = txt_file.readlines()

    in_table_of_contents = True
    previous_line = ""

    for line in lines:
        # If we reach the line "Notes", we are out of table of contents.
        if "Notes" in line:
            in_table_of_contents = False

        # Check if this line starts a new chapter and we are not in table of contents.
        if line.startswith('Chapter ') and not in_table_of_contents:
            line = '## ' + line

        # If this line is not empty or previous line is not empty, write the line.
        # This avoids writing multiple consecutive newlines.
        if line.strip() or previous_line.strip():
            md_file.write(line)

        previous_line = line


txt_to_md(sys.stdin, sys.stdout)

