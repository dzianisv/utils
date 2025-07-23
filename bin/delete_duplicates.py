#!/usr/bin/env python3
import os
import sys

def parse_duplicates(lines):
    to_delete = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.strip().endswith("bytes each:"):
            i += 1  # skip header
            # The first file (keep)
            if i < len(lines):
                i += 1  # skip the first file (do not delete)
            # All subsequent files in the group (delete)
            while i < len(lines) and lines[i].strip() and not lines[i].strip().endswith('bytes each:'):
                parts = lines[i].split()
                if len(parts) >= 3:
                    path = parts[2]
                    to_delete.append(path)
                i += 1
        else:
            i += 1
    return to_delete

def main():
    do_delete = "--delete" in sys.argv
    # Read input from stdin
    lines = [line for line in sys.stdin]
    files_to_delete = parse_duplicates(lines)

    if not do_delete:
        print("Dry-run mode: The following files would be deleted:")
        for path in files_to_delete:
            print(path)
        print(f"\nTo actually delete, use: ... | {sys.argv[0]} --delete")
    else:
        for path in files_to_delete:
            try:
                os.remove(path)
                print(f"Deleted: {path}")
            except Exception as e:
                print(f"Error deleting {path}: {e}")

if __name__ == "__main__":
    main()

