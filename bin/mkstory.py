#!/usr/bin/env python3

import ffmpeg
import sys
import logging


def get_resolution(file):
    probe = ffmpeg.probe(file)
    video_stream = next((stream for stream in probe['streams'] if stream['codec_type'] == 'video'), None)
    if video_stream is None:
        return None

    width = int(video_stream['width'])
    height = int(video_stream['height'])
    return  width, height

def main():
    input_file = sys.argv[1]
    
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
    ffmpeg.input(input_file).filter('scale', scaled_resolution[0], scaled_resolution[1]).crop(crop_offset[0], crop_offset[1], target_resolution[0], target_resolution[1]).output("story.mp4", crf=23).run()
    
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()