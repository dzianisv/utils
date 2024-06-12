#!/usr/bin/env python3

import os
import sys
import subprocess

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
                    with open(os.path.join(root, file), 'r', encoding='utf-8') as infile:
                        outfile.write(infile.read())
                    outfile.write("\n>>>\n")

if __name__ == "__main__":
    # Check if the correct number of arguments are provided
    if len(sys.argv) != 3:
        print("Usage: python script.py <input_directory> <output_file>")
        sys.exit(1)

    # Get the input directory and output file from the arguments
    input_directory = sys.argv[1]
    output_file = sys.argv[2]

    # Get the git URL
    git_url = get_git_url(input_directory)

    # Call the consolidate_files function
    consolidate_files(input_directory, output_file, git_url)
