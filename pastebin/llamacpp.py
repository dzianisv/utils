#!/usr/bin/env python3

import openai
import os

client = openai.OpenAI(base_url=os.environ.get("API_BASE", "http://localhost:8080"), api_key=os.environ.get("API_KEY", ""))

def transcribe(file_path: str) -> str:
    # Perform transcription
    with open(file_path, 'rb') as audio_file:
        return client.audio.transcribe(
            model="whisper-1",
            file=audio_file
        )


if __name__ == "__main__":
    import sys
    print(transcribe(sys.argv[1]))