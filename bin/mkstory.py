#!/usr/bin/env python3

import ffmpeg
import os
import logging
import argparse

def get_resolution(file):
    probe = ffmpeg.probe(file)
    video_stream = next((stream for stream in probe['streams'] if stream['codec_type'] == 'video'), None)
    if video_stream is None:
        return None

    width = int(video_stream['width'])
    height = int(video_stream['height'])
    return  width, height

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("-ss", help="Start offset (seconds)", type=str, default="0")
    parser.add_argument("input_file", nargs="?", help="input media file")
    parser.add_argument("--audio", type=str, help='audio track', default=None)
    parser.add_argument("--caption", type=str, default="", help="story caption")

    args = parser.parse_args()
    input_file = args.input_file
    
    fontfile = os.path.join(os.path.dirname(__file__), 'Comfortaa.ttf')

    source_resolution=get_resolution(input_file)
    target_resolution=(1080, 1920)
    ratio = target_resolution[0]/target_resolution[1]
    
    scale_factor = 0

    if target_resolution[0] != source_resolution[0]:
        scale_factor = max(scale_factor, target_resolution[0]/source_resolution[0])
    
    if target_resolution[1] != source_resolution[1]:
        scale_factor = max(scale_factor, target_resolution[1]/source_resolution[1])
    
    if scale_factor == 0:
        scale_factor = 1

    scaled_resolution = (source_resolution[0] * scale_factor, source_resolution[1] * scale_factor)
    crop_offset = ((scaled_resolution[0]-target_resolution[0])/2, (scaled_resolution[1] - target_resolution[1])/2)

    logging.info("%s %s", scaled_resolution, crop_offset)
    input = ffmpeg.input(input_file)
    video = input.video.filter('scale', scaled_resolution[0], scaled_resolution[1]).crop(crop_offset[0], crop_offset[1], target_resolution[0], target_resolution[1]).drawtext(fontfile=fontfile, fontsize=40, fontcolor='white', alpha=0.60, text=args.caption, x="(w-text_w-line_h)", y="(h-text_h-line_h)")
    audio = input.audio if args.audio is None else ffmpeg.input(args.audio).audio

    ffmpeg.output(audio, video, "story.mp4", acodec='aac', vcodec='h264', crf=23, t=15, ss=args.ss).run()
    
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()