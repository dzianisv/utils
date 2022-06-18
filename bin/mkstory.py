#!/usr/bin/env python3
# python3 -m pip install -U ffmpeg-python
import ffmpeg
import os
import logging
import argparse
from enum import Enum

def get_resolution(file):
    metadata = ffmpeg.probe(file)
    video_stream = next((stream for stream in metadata['streams'] if stream['codec_type'] == 'video'), None)
    if video_stream is None:
        return None

    width = int(video_stream['width'])
    height = int(video_stream['height'])
    
    if 'tags' in video_stream and 'rotate' in video_stream['tags'] and int(video_stream['tags']['rotate']) == 90:
        return height, width
    else:
        return  width, height

def get_duration(file):
    metadata = ffmpeg.probe(file)
    return float(metadata['format']['duration'])


class GravityType(Enum):
    CENTER = "center"
    LEFT = "left"
    RIGHT = "right"

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("-ss", help="Start offset (seconds)", type=int, default="0")
    parser.add_argument("input_file", nargs="?", help="input media file")
    parser.add_argument("-t", type=int, help="ffmpeg -t, duration", default=15)
    parser.add_argument("--audio", type=str, help='audio track', default=None)
    parser.add_argument("--caption", type=str, default="", help="story caption")
    parser.add_argument("--caption-font", type=str, default="Comforta", help="Font to draw caption")
    parser.add_argument("--caption-fontfile", type=str, default=None, help="Font file to draw caption")
    parser.add_argument("--gravity", type=GravityType, default=GravityType.CENTER, help="Crop gravity")
    parser.add_argument("--offset", type=float, default=1.0, help="X offset ratio")
    args = parser.parse_args()
    input_file = args.input_file
    
    source_resolution=get_resolution(input_file)
    target_resolution=(1080, 1920)
    ratio = target_resolution[0]/target_resolution[1]
    
    scale_factor = 0

    if target_resolution[0] != source_resolution[0]:
        scale_factor = max(scale_factor, target_resolution[0]/source_resolution[0])
    
    if target_resolution[1] != source_resolution[1]:
        scale_factor = max(scale_factor, target_resolution[1]/source_resolution[1])

    scaled_resolution = (source_resolution[0] * scale_factor, source_resolution[1] * scale_factor)
    if args.gravity == GravityType.CENTER:
        crop_offset = ((scaled_resolution[0]-target_resolution[0])/2 * args.offset, (scaled_resolution[1] - target_resolution[1])/2)
    elif args.gravity == GravityType.LEFT:
        crop_offset = (0, (scaled_resolution[1] - target_resolution[1])/2)
    
    logging.info("%s %s", scaled_resolution, crop_offset)

    # https://ffmpeg.org/ffmpeg-filters.html#drawtext-1
    drawtext_opt = {}
    if args.caption_fontfile:
        drawtext_opt["fontfile"] = args.caption_fontfile
    elif args.caption_font:
        drawtext_opt["font"] = args.caption_font
    drawtext_opt["text"] = args.caption.replace("\\n", "\n")

    offset = int(args.ss)
    i = 0
    output_prefix = os.path.basename(input_file)

    input = ffmpeg.input(input_file)
    duration = get_duration(input_file)

    while offset < duration:
        input = ffmpeg.input(input_file)
        video = input.video.filter('scale', scaled_resolution[0], scaled_resolution[1]).crop(crop_offset[0], crop_offset[1], target_resolution[0], target_resolution[1]).drawtext(fontsize=40, fontcolor='white', alpha=0.60, x="(w-text_w-line_h)", y="(h-text_h-line_h)", **drawtext_opt)
        audio = input.audio if args.audio is None else ffmpeg.input(args.audio).audio
        ffmpeg.output(audio, video, f"{output_prefix}-{i}.mp4", acodec='aac', vcodec='h264', crf=23, t=args.t, ss=offset).run()
        offset += int(args.t)
        i += 1

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()
