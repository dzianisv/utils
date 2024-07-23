#!/usr/bin/env python3

# pip install git+https://github.com/m-bain/whisperx.git

import whisperx
import argparse
import io


def transcribe(audio_file: str):
    device = "cpu"
    audio_file
    model = "small"
    batch_size = 16 # reduce if low on GPU mem
    compute_type = "int8" # change to "int8" if low on GPU mem (may reduce accuracy)

    # 1. Transcribe with original whisper (batched)
    model = whisperx.load_model(model, device, compute_type=compute_type)
    audio = whisperx.load_audio(audio_file)
    result = model.transcribe(audio, batch_size=batch_size)

    # 2. Align whisper output
    model_a, metadata = whisperx.load_align_model(language_code=result["language"], device=device)
    aligned_result = whisperx.align(result["segments"], model_a, metadata, audio, device, return_char_alignments=False)
    result.update(aligned_result)
    return result


def create_subtitles(result: dict, stream: io.TextIOBase):
    writer = whisperx.utils.WriteVTT(".")
    writer.write_result(result, stream, {"max_line_width": 32, "max_line_count": 2, "highlight_words": True})
    return stream


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("audio_file", type=str)
    args = parser.parse_args()
    result = transcribe(args.audio_file)
    print(result)

    stream = io.StringIO()
    create_subtitles(result, stream)
    print(stream.getvalue())

if __name__ == "__main__":
    main()
