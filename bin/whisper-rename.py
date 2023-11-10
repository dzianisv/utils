#!/usr/bin/env python3

import os
import sys
import openai

def transcribe(file):
    # Read the contents of the file
    with open(file, 'rb') as f:
        response = openai.Audio.transcribe("whisper-1", f)
        print(file, response["text"])
        return response["text"]

if __name__ == "__main__":
    # Check if there are any files passed as arguments
    for file in sys.argv[1:]:
        extension = os.path.splitext(file)[1]
        transcription = transcribe(file)

        dirname = os.path.dirname(file)
        new_path = os.path.join(dirname, transcription + extension)
        os.rename(file, new_path)