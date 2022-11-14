#!/bin/bash

# some videos seem to refuse to reduce its resolution
for f in *.mp4; do
    ffmpeg -i $f -vf scale=180:360 -preset slow -crf 18 -vsync passthrough reduced_$f;
done;

# count frames
ffprobe \
-v error \
-select_streams v:0 -count_frames \
-show_entries stream=nb_read_frames \
-print_format csv reduced_04161FQCB00182_video_0_a6b13d7f-4e05-4824-8d32-4eadc3274a2e.mp4

# count file in directory
ls -f | wc -l

# measure memory size
du -sh .

# get free GB
free -g -h -t

# copy every 4th video
cp $(printf '%s\n' 1*.mp4 | awk 'NR%4 == 1') ../flicker-chunks/
