#!/usr/bin/env python3
import sys
import re

def clean_subtitles():
    for line in sys.stdin:
        # Remove HTML-like tags
        clean_line = re.sub(r'<[^>]+>', '', line)
        
        # Check if the line contains a timestamp
        if '-->' in clean_line:
            # Extract the start timestamp
            timestamp = clean_line.split('-->')[0].strip()
            sys.stdout.write(f"{timestamp}\n")
        elif clean_line.strip() and not clean_line.strip().isdigit():
            # Write non-empty lines that are not sequence numbers
            sys.stdout.write(clean_line)
        else:
            # Add a blank line to separate subtitle entries
            sys.stdout.write('\n')

if __name__ == "__main__":
    clean_subtitles()
