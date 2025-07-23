#!/usr/bin/env python3
import sys
import openai

audio_file= open(sys.argv[1], "rb")
response = openai.Audio.transcribe("whisper-1", audio_file)
print(response["text"])