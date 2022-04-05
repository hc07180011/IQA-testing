import os
import json
import logging
from typing import Tuple
from argparse import ArgumentParser

import cv2
import tqdm
import numpy as np
import tensorflow as tf

from sklearn.model_selection import train_test_split
from imblearn.over_sampling import SMOTE
from keras.models import Sequential
from keras.layers import LSTM, Dense, Flatten, Bidirectional


from mypyfunc.keras import Model, InferenceModel
from mypyfunc.logger import init_logger
from preprocessing.embedding.facenet import Facenet


data_base_dir = "data"
os.makedirs(data_base_dir, exist_ok=True)
cache_base_dir = ".cache"
os.makedirs(cache_base_dir, exist_ok=True)


def _embed(
    video_data_dir: str,
    output_dir: str
) -> None:
    os.makedirs(output_dir, exist_ok=True)

    facenet = Facenet()
    for path in tqdm.tqdm(os.listdir(video_data_dir)):
        if os.path.exists(os.path.join(output_dir, "{}.npy".format(path))):
            continue

        vidcap = cv2.VideoCapture(os.path.join(video_data_dir, path))
        success, image = vidcap.read()

        embeddings = ()
        while success:
            embeddings = embeddings + tuple(facenet.get_embedding(cv2.resize(
                image, (200, 200)), batched=False).flatten())
            success, image = vidcap.read()

        embeddings = np.array(embeddings)

        np.save(os.path.join(output_dir, path), embeddings)


def _get_chunk_array(input_arr: np.array, chunk_size: int) -> Tuple:
    # usable_vec = input_arr[:(
    #     np.floor(len(input_arr)/chunk_size)*chunk_size).astype(int)]

    # i_pad = np.concatenate((usable_vec, np.array(
    #     [input_arr[-1]]*(chunk_size-len(usable_vec) % chunk_size))))
    asymmetric_chunks = np.split(
        # i_pad,
        input_arr,
        list(range(
            chunk_size,
            input_arr.shape[0] + 1,
            chunk_size
        ))
    )
    return tuple(asymmetric_chunks[:-1])


def _preprocess(
    label_path: str,
    mapping_path: str,
    data_dir: str,
    cache_path: str
) -> Tuple[np.array]:
    """
    can consider reducing precision of np.float32 to np.float16 to reduce memory consumption

    abstract:
    https://towardsdatascience.com/overcoming-data-preprocessing-bottlenecks-with-tensorflow-data-service-nvidia-dali-and-other-d6321917f851
    cuda solution:
    https://stackoverflow.com/questions/60996756/how-do-i-assign-a-numpy-int64-to-a-torch-cuda-floattensor
    static memory allocation solution:
    https://pytorch.org/docs/stable/generated/torch.zeros.html
    """
    if os.path.exists("{}.npz".format(cache_path)):
        __cache__ = np.load("{}.npz".format(cache_path), allow_pickle=True)
        return tuple((__cache__[k] for k in __cache__))

    pass_videos = list([
        "0096.mp4", "0097.mp4", "0098.mp4",
        "0125.mp4", "0126.mp4", "0127.mp4",
        "0145.mp4", "0146.mp4", "0147.mp4",
        "0178.mp4", "0179.mp4", "0180.mp4"
    ])
    raw_labels = json.load(open(label_path, "r"))
    encoding_filename_mapping = json.load(open(mapping_path, "r"))

    embedding_path_list = sorted([
        x for x in os.listdir(data_dir)
        if x.split(".npy")[0] not in pass_videos
        and encoding_filename_mapping[x.replace(".npy", "")] in raw_labels
    ])

    embedding_list_train, embedding_list_test, _, _ = train_test_split(
        embedding_path_list,
        list(range(len(embedding_path_list))),
        test_size=0.1,
        random_state=42
    )

    chunk_size = 30

    video_embeddings_list_train = ()
    video_labels_list_train = ()
    logging.debug(
        "taking training chunks, length = {}".format(len(embedding_list_train))
    )
    for path in tqdm.tqdm(embedding_list_train):
        real_filename = encoding_filename_mapping[path.replace(".npy", "")]

        buf_embedding = np.load(os.path.join(data_dir, path))
        if buf_embedding.shape[0] == 0:
            continue

        video_embeddings_list_train = video_embeddings_list_train + \
            (*_get_chunk_array(buf_embedding, chunk_size),)

        flicker_idxs = np.array(raw_labels[real_filename]) - 1
        buf_label = np.zeros(buf_embedding.shape[0]).astype(
            np.uint8) if buf_embedding.shape[0] > 0 else (0,)*(flicker_idxs+1)
        buf_label[flicker_idxs] = 1
        video_labels_list_train = video_labels_list_train + tuple(
            1 if sum(x) else 0
            for x in _get_chunk_array(buf_label, chunk_size)
        )

    video_embeddings_list_test = ()
    video_labels_list_test = ()
    logging.debug(
        "taking testing chunks, length = {}".format(len(embedding_list_test))
    )
    for path in tqdm.tqdm(embedding_list_test):
        real_filename = encoding_filename_mapping[path.replace(".npy", "")]

        buf_embedding = np.load(os.path.join(data_dir, path))
        if buf_embedding.shape[0] == 0:
            continue

        video_embeddings_list_test = video_embeddings_list_test + \
            (*_get_chunk_array(buf_embedding, chunk_size),)

        flicker_idxs = np.array(raw_labels[real_filename]) - 1
        buf_label = np.zeros(buf_embedding.shape[0]).astype(np.uint8)
        buf_label[flicker_idxs] = 1
        video_labels_list_test = video_labels_list_test + tuple(
            1 if sum(x) else 0
            for x in _get_chunk_array(buf_label, chunk_size)
        )
    X_train = np.array(video_embeddings_list_train)
    X_test = np.array(video_embeddings_list_test)
    y_train = np.array(video_labels_list_train)
    y_test = np.array(video_labels_list_test)

    logging.debug("ok. got training: {}/{}, testing: {}/{}".format(
        X_train.shape, y_train.shape,
        X_test.shape, y_test.shape
    ))

    np.savez(cache_path, X_train, X_test, y_train, y_test)

    return (X_train, X_test, y_train, y_test)


def _oversampling(
    X_train: np.array,
    y_train: np.array,
) -> Tuple[np.array]:
    """
    batched alternative:
    https://imbalanced-learn.org/stable/references/generated/imblearn.keras.BalancedBatchGenerator.html
    """
    train_path = os.path.join(
        data_base_dir, "flicker_detection_model_architecture/X_train.npy")
    test_path = os.path.join(
        data_base_dir, "flicker_detection_model_architecture/y_train.npy")

    if os.path.exists(train_path) and os.path.exists(test_path):
        X_train, y_train = np.load(train_path), np.load(test_path)
        logging.info("{}{}".format(X_train.shape, y_train.shape))
        return X_train, y_train

    sm = SMOTE(random_state=42)
    original_X_shape = X_train.shape
    X_train, y_train = sm.fit_resample(
        np.reshape(X_train, (-1, np.prod(original_X_shape[1:]))),
        y_train
    )
    X_train = np.reshape(X_train, (-1,) + original_X_shape[1:])
    np.save("X_train.npy", X_train)
    np.save("y_train.npy", y_train)
    return (X_train, y_train)


def _train(X_train: np.array, y_train: np.array) -> object:
    buf = Sequential()
    buf.add(Bidirectional(LSTM(units=256, activation='relu'),
                          input_shape=(X_train.shape[1:])))
    buf.add(Dense(units=128, activation="relu"))
    buf.add(Flatten())
    buf.add(Dense(units=1, activation="sigmoid"))

    model = Model(
        model=buf,
        loss="binary_crossentropy",
        optimizer=tf.keras.optimizers.Adam(learning_rate=1e-5),
    )
    model.train(X_train, y_train, 1000, 0.1, 1024)
    for k in list(("loss", "accuracy", "f1", "auc")):
        model.plot_history(k, title="{} - LSTM, Chunk, Oversampling".format(k))

    return model


def _test(model_path: str, X_test: np.array, y_test: np.array) -> None:
    model = InferenceModel(model_path)
    y_pred = model.predict(X_test)
    model.evaluate(y_test, y_pred)


def _main() -> None:
    parser = ArgumentParser()
    parser.add_argument(
        "-train", "--train", action="store_true",
        default=False,
        help="Whether to do training"
    )
    parser.add_argument(
        "-test", "--test", action="store_true",
        default=False,
        help="Whether to do testing"
    )
    args = parser.parse_args()

    init_logger()

    logging.info("[Embedding] Start ...")
    _embed(
        os.path.join(data_base_dir, "flicker-detection"),
        os.path.join(data_base_dir, "embedding")
    )
    logging.info("[Embedding] done.")

    logging.info("[Preprocessing] Start ...")
    X_train, X_test, y_train, y_test = _preprocess(
        os.path.join(data_base_dir, "label.json"),
        os.path.join(data_base_dir, "mapping.json"),
        os.path.join(data_base_dir, "embedding"),
        os.path.join(cache_base_dir, "train_test")
    )
    logging.info("[Preprocessing] done.")

    logging.info("[Oversampling] Start ...")
    X_train, y_train = _oversampling(
        X_train,
        y_train
    )
    logging.info("[Oversampling] done.")

    if args.train:
        logging.info("[Training] Start ...")
        _ = _train(
            X_train,
            y_train
        )
        logging.info("[Training] done.")

    if args.test:
        logging.info("[Testing] Start ...")
        _test("model.h5", X_test, y_test)
        logging.info("[Testing] done.")


if __name__ == "__main__":
    _main()
    # vimdiff ~/googlecv/train.py /home/henrychao/googlecv/train.py
    # https://github.com/3b1b/manim/issues/1213 opencv issue
