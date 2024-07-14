#!/usr/bin/env python3

import openai
import os

client = openai.OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

def transcript(file_path: str) -> str:
    # Perform transcription
    with open(file_path, 'rb') as audio_file:
        # https://platform.openai.com/docs/api-reference/audio/createTranscription?lang=python
        transcript = client.audio.transcriptions.create(
            file=audio_file,
            model="whisper-1",
            response_format="verbose_json",
            timestamp_granularities=["word"]
        )
        return transcript


if __name__ == "__main__":
    import sys
    print(transcript(sys.argv[1]))