#!/usr/bin/env python3

import os
import sys
import subprocess
import tempfile
import shutil
import logging

logger = logging.getLogger(__name__)

def get_git_url(directory):
    try:
        # Run the git command to get the remote URL
        result = subprocess.run(['git', 'remote', 'get-url', 'origin'], cwd=directory, capture_output=True, text=True)
        result.check_returncode()
        git_url = result.stdout.strip()

        # Remove the .git suffix if present
        if git_url.endswith('.git'):
            git_url = git_url[:-4]

        # Add the base path for GitHub files
        git_url = git_url.replace('git@github.com:', 'https://github.com/')
        git_url = git_url.replace('.git', '')
        return git_url
    except subprocess.CalledProcessError:
        print("Error: Not a git repository or no remote URL found.")
        sys.exit(1)

def consolidate_files(input_directory, output_file, git_url):
    # Define the file extensions to look for
    file_extensions = [
        '.c', '.cpp', '.cs', '.java', '.js', '.ts', '.go', '.py', '.rb', '.php', '.html', '.css', '.scss', '.md',
        '.txt', '.xml', '.json', '.yaml', '.yml', '.sh', '.bat', '.pl', '.rs', '.swift', '.kt', '.m', '.mm', '.r',
        '.jl', '.sql'
    ]

    # Open the output file in write mode
    with open(output_file, 'w', encoding='utf-8') as outfile:
        # Walk through the directory
        for root, dirs, files in os.walk(input_directory):
            for file in files:
                # Check if the file has one of the desired extensions
                if any(file.endswith(ext) for ext in file_extensions):
                    file_path = os.path.relpath(os.path.join(root, file), input_directory)
                    # Generate the GitHub URL for the file
                    github_file_url = f"{git_url}/blob/main/{file_path}".replace('\\', '/')
                    # Write the file path to the output file
                    outfile.write(f"{github_file_url}\n")
                    outfile.write("<<<\n")
                    # Write the file content to the output file
                    with open(os.path.join(root, file), 'rb') as infile:
                        content = infile.read().decode(encoding='utf-8', errors='ignore')
                        outfile.write(content)
                    outfile.write("\n>>>\n")

def main():
    # Check if the correct number of arguments are provided
    if len(sys.argv) < 2:
        print("Usage: python script.py <input_directory> <output_file>")
        sys.exit(1)

    # Get the input directory and output file from the arguments
    source_arg = sys.argv[1]
    output_file = sys.argv[2] if len(sys.argv) > 2 else os.path.basename(source_arg) + '.txt'

    work_dir = None
    try:
        if source_arg.startswith("https://github.com"):
            git_url = source_arg
            work_dir = tempfile.TemporaryDirectory()
            doc_dir = work_dir.name
            subprocess.run(['git', 'clone', source_arg, doc_dir], check=True)

        else:
            doc_dir = source_arg
            git_url = get_git_url(doc_dir)

        logger.info(f"doc_dir={doc_dir}, output_file={output_file}")


        # Call the consolidate_files function
        consolidate_files(doc_dir, output_file, git_url)
        return 0
    finally:
        if type(work_dir) is tempfile.TemporaryDirectory:
            shutil.rmtree(work_dir.name)


if __name__ == "__main__":
    sys.exit(main())