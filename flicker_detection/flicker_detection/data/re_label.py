import os
import json
import cv2
import matplotlib
import numpy as np
import matplotlib.pyplot as plt


def save_flicker_img(vid_path: str, init_sec, flicker_frames: list = None, raw_name=None) -> None:
    cap = cv2.VideoCapture(vid_path)
    fps = cap.get(cv2.CAP_PROP_FPS)
    window = [0]*3
    success, frame = True, 0
    while success:
        success, img = cap.read()
        window[frame % 3] = img

        if flicker_frames and (frame in flicker_frames):
            show_images([window[(frame - 2) % 3], window[(frame - 1) % 3], window[frame % 3]],
                        save=True,
                        filename=f"flicker_images/{vid_path[-8:-4] if raw_name is None else raw_name}_frame_{frame}.jpg")
        elif flicker_frames is None and frame >= (init_sec * fps) and frame <= (init_sec + 1) * fps:
            cv2.imwrite(
                f"flicker_images/{vid_path[-8:-4] if raw_name is None else raw_name}_frame_{frame}.jpg", img)

        frame += int(success)
    cap.release()


def label_aug():
    mapping = json.load(open("mapping.json", "r"))
    vids = dict(map(lambda s: (s[:4], s), mapping.keys()))
    for aug_vid in os.listdir("augmented/"):
        if aug_vid[:4] in vids:
            mapping[aug_vid] = mapping[vids[aug_vid[:4]]]
    json.dump(mapping, open("mapping_test.json", "w"))


def read_proto_string():
    with open('new_label.textproto', 'r') as f:
        lines = f.readlines()
    dic = {}
    vid_name = None
    for line in lines:
        if 'video' in line:
            vid_name = str(line[10:-2])
            if vid_name not in dic.keys():
                dic[vid_name] = None
        if 'frame' in line and 'flicker' not in line:
            if not dic[vid_name] and ',' in line:
                dic[vid_name] = list(
                    map(int, line[10:-2].replace(' ', '').split(',')))
            elif not dic[vid_name] and line[10:-2] != '':
                dic[vid_name] = [int(line[10:-2])]
            elif dic[vid_name] and ',' in line:
                dic[vid_name].extend(list(
                    map(int, line[10:-2].replace(' ', '').split(','))))
            elif dic[vid_name] and line[10:-2] != '':
                dic[vid_name].append(int(line[10:-2]))

    with open('new_label.json', 'w') as out:
        json.dump(dic, out)
    return dic


def writeimg_new_labels():
    matplotlib.use('Agg')
    plt.ioff()
    raw_labels = json.load(open('new_label.json', 'r'))
    mapping = json.load(open('mapping.json', "r"))
    inv_map = {v: k for k, v in mapping.items()}
    for vid in raw_labels:
        if inv_map[vid] in mapping.keys():
            save_flicker_img(
                f'flicker-detection/{inv_map[vid]}', 1, raw_labels[vid], raw_name=vid)
        plt.close('all')
        print(vid)


def show_images(images: list[np.ndarray], save=False, filename=None) -> None:
    f = plt.figure(figsize=(10, 6))
    for idx, img in enumerate(images):
        f.add_subplot(1, len(images), idx + 1)
        plt.imshow(img)
    plt.savefig(filename) if save else plt.show(block=True)


def merge(d1, d2, merge):
    result = dict(d1)
    for k, v in d2.items():
        if k in result:
            result[k] = merge(result[k], v)
        else:
            result[k] = v
    return result


def manual_label(vid_path: str,):
    cap = cv2.VideoCapture(vid_path)
    h, w, total, fps = cap.get(cv2.CAP_PROP_FRAME_HEIGHT), cap.get(
        cv2.CAP_PROP_FRAME_WIDTH), cap.get(cv2.CAP_PROP_FRAME_COUNT), cap.get(cv2.CAP_PROP_FPS)
    vid_arr = [0]*(int(total)+1)
    frame_count, success, labels = 0, True, {}
    while success:
        success, vid_arr[frame_count] = cap.read()
        frame_count += int(success)
    cap.release()

    labels[vid_path] = []
    cur_frame = int(
        input(f"Choose frame idx: frames from 0 - {int(total)}\n"))
    while cur_frame < total:

        show_images(
            [vid_arr[cur_frame-2], vid_arr[cur_frame-1], vid_arr[cur_frame]])
        r = str(input("Save set?[y/n/q]\n"))
        if r == 'q':
            break
        if r == 'y':
            labels[vid_path].extend([cur_frame])

        cur_frame = int(
            input(f"Choose frame idx: frames from 0 - {int(total)}\n"))

    if os.path.exists("manual_labels.json"):
        with open("manual_labels.json", 'r') as infile:
            existing = json.load(infile)
            labels = merge(existing, labels, lambda x, y: (x, y))

    with open("manual_labels.json", "w") as out:
        json.dump(labels, out)
    return h, w, total


def check_fps(vid_path: str) -> bool:
    """
    problem only from opencv 3 ?
    """
    cap = cv2.VideoCapture(vid_path)
    fps = cap.get(cv2.CAP_PROP_FPS)
    print(cap.set(cv2.CAP_PROP_POS_AVI_RATIO, 1))
    print(cap.get(cv2.CAP_PROP_POS_MSEC))
    print(cap.get(cv2.CAP_PROP_POS_FRAMES))
    print(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    print(cap.set(cv2.CAP_PROP_POS_AVI_RATIO, 0))
    print(cap.get(cv2.CAP_PROP_POS_FRAMES))
    num_frames, ret = 0, True
    while ret:
        ret, frame = cap.read()
        if ret:
            num_frames += 1
    duration = float(num_frames) / float(fps)  # in seconds
    print(f"FPS - {fps}\nSeconds - {duration}\nNum_frames - {num_frames}\n\n")
    cap.release()
    return True


if __name__ == "__main__":
    """
    sudomen

    ffmpeg -i video.mp4 -vf select='between(n\,x\,y)' -vsync 0 -start_number x frames%d.png
    for ex if the label frame is 475, i will run:
    ffmpeg -i in.mp4 -vf select='between(n\,460\,490)' -vsync 0 -start_number 475 frames%d.png
    correct:
    ffmpeg -i in.mp4 -vf select='between(n\,460\,490)' -vsync 0 -start_number 460 frames%d.png

    fyi the command to get the frame pts
    ffprobe -i test_01.mp4 -show_frames | grep pkt_pts_time

    Convert variable frame rate to standard fps
    for file in flicker-detection/*; 
        do ffmpeg -y -i $file -c copy -f h264 "h264_vids/${file:18:4}.h264"; 
    done
    for file in h264_vids/*; 
        do ffmpeg -y -r 30 -i $file -c copy "standard_fps_vid/${file:10:4}.mp4"; 
    done

    for file in augmented/*; 
       do ffmpeg -y -i $file -c copy -f h264 "h264_vids/${file:10:6}.h264"; 
    done

    for file in h264_vids/*; 
        do ffmpeg -y -r 30 -i $file -c copy "standard_fps_vid/${file:10:6}.mp4"; 
    done
    Check frame count ffmpeg
    ffmpeg -i "path to file" -f null /dev/null

    ?????? opencv problem?
    https://github.com/opencv/opencv/issues/17257

    # ffprobe -i test_01.mp4 -show_frames -select_streams v:0 -print_format flat | grep pkt_pts_time=
    ffmpeg
    """
    # save_flicker_img("flicker-detection/0145.mp4", 13)
    # read_proto_string()
    # writeimg_new_labels()
    # manual_label('flicker-detection/0136.mp4')
    # for vid in os.listdir('standard_fps_vid/'):
    #     check_fps(os.path.join('standard_fps_vid/',vid))
    # check_fps('flicker-detection/0001.mp4')
    label_aug()
