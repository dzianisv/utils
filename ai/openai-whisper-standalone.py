#!/usr/bin/env python3

import whisper
import argparse

def main():

    parser = argparse.ArgumentParser()
    parser.add_argument("--model", type=str, default='base', help="model to use: tiny, base, samll, medium, large; https://github.com/openai/whisper?tab=readme-ov-file#available-models-and-languages")
    parser.add_argument("audio_file", type=str, help="audio file to transcribe")
    args = parser.parse_args()

    model = whisper.load_model(args.model)

    # load audio and pad/trim it to fit 30 seconds
    audio = whisper.load_audio(args.audio_file)
    audio = whisper.pad_or_trim(audio)

    # make log-Mel spectrogram and move to the same device as the model
    mel = whisper.log_mel_spectrogram(audio).to(model.device)

    # # detect the spoken language
    # _, probs = model.detect_language(mel)
    # print(f"Detected language: {max(probs, key=probs.get)}")

    # decode the audio
    options = whisper.DecodingOptions()
    result = whisper.decode(model, mel, options)

    # print the recognized text
    print(result.text)

main()
