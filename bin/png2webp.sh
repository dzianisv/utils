#!/bin/sh
set -e
for i in *.png; do  convert $i ${i%.*}.webp; done;