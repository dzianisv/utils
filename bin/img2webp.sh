#!/bin/bash


for i in "$*"; do name=${i%.*}; convert $i $name.webp;  done;
