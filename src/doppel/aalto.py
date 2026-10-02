"""Loads participants from the Aalto 136M Keystrokes dataset as Doppel records.

The dataset (Dhakal, Feit, Kristensson, Oulasvirta, CHI 2018;
https://userinterfaces.aalto.fi/136Mkeystrokes/) is one 1.57 GB zip holding a
tab-separated file per participant (15 typed sentences, one row per
keystroke: press and release time in ms, JavaScript key code) and a metadata
file. It is read straight from the zip, never unzipped (16 GB).

How it works:
    1. eligible_participants(): from the metadata, keep people who used a
       QWERTY layout on a physical keyboard (full or laptop).
    2. load_sentences(): read one participant's file, group rows by sentence
       and order the sentences by when they were started.
    3. load_sample(): go through the eligible participants in a random order
       (from the caller's random generator, so experiments are repeatable),
       replay each sentence separately through Doppel's collector (pairs
       never span two sentences), split by time into training sentences and
       test sentences, and keep people with all sentences and enough test
       records, until n participants are loaded.
"""

import csv
import zipfile
from collections.abc import Callable
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from doppel.keymap import relation
from doppel.records import KeystrokeRecord
from doppel.replay import replay

ZIP_PATH = Path("data") / "aalto" / "Keystrokes.zip"
FILES = "Keystrokes/files/"


def read_tsv(z: zipfile.ZipFile, name: str, **kwargs) -> pd.DataFrame:
    """Read a tab-separated file from the zip (sentences may contain quotes)."""
    with z.open(name) as f:
        return pd.read_csv(
            f,
            sep="\t",
            quoting=csv.QUOTE_NONE,
            encoding_errors="replace",
            on_bad_lines="skip",
            **kwargs,
        )


def eligible_participants(z: zipfile.ZipFile) -> np.ndarray:
    """Return the ids of participants on a QWERTY physical keyboard."""
    meta = read_tsv(z, f"{FILES}metadata_participants.txt")
    keep = (meta["LAYOUT"] == "qwerty") & meta["KEYBOARD_TYPE"].isin(["full", "laptop"])
    return meta[keep]["PARTICIPANT_ID"].to_numpy()


def load_sentences(z: zipfile.ZipFile, pid: int) -> list[list[tuple[float, float, int]]]:
    """Return a participant's sentences in typing order, as keystroke lists."""
    rows = read_tsv(
        z,
        f"{FILES}{pid}_keystrokes.txt",
        usecols=["TEST_SECTION_ID", "PRESS_TIME", "RELEASE_TIME", "KEYCODE"],
    )
    rows = rows.apply(pd.to_numeric, errors="coerce").dropna()
    sentences = []
    for _, s in rows.groupby("TEST_SECTION_ID"):
        keystrokes = list(zip(s["PRESS_TIME"], s["RELEASE_TIME"], s["KEYCODE"].astype(int)))
        sentences.append((s["PRESS_TIME"].min(), keystrokes))
    sentences.sort(key=lambda item: item[0])  # by when the sentence started
    return [keystrokes for _, keystrokes in sentences]


def to_records(
    sentences: list[list[tuple[float, float, int]]],
    label_fn: Callable[[int, int], Any] = relation,
) -> list[KeystrokeRecord]:
    """Replay each sentence separately (pairs never span two sentences)."""
    records = []
    for keystrokes in sentences:
        records += replay(keystrokes, label_fn=label_fn)
    return records


def load_sample(
    z: zipfile.ZipFile,
    rng: np.random.Generator,
    n: int,
    label_fn: Callable[[int, int], Any] = relation,
    train_sentences: int = 10,
    test_sentences: int = 5,
    min_test_records: int = 100,
) -> tuple[dict[int, tuple[list[KeystrokeRecord], list[KeystrokeRecord]]], int]:
    """Load n participants as (training records, test records).

    Args:
        z: the open dataset zip.
        rng: random generator that orders the eligible participants.
        n: participants to load.
        label_fn: label for each pair (Doppel's relation by default).
        train_sentences: first sentences used for training.
        test_sentences: following sentences used for testing.
        min_test_records: participants with fewer test records are skipped.

    Returns:
        (participant id -> (train records, test records), number eligible).
    """
    eligible = eligible_participants(z)
    data = {}
    for pid in rng.permutation(eligible):
        if len(data) == n:
            break
        try:
            sentences = load_sentences(z, int(pid))
        except (KeyError, ValueError):
            continue  # missing or unreadable file
        if len(sentences) < train_sentences + test_sentences:
            continue
        train = to_records(sentences[:train_sentences], label_fn)
        test = to_records(sentences[train_sentences : train_sentences + test_sentences], label_fn)
        if len(test) < min_test_records:
            continue
        data[pid] = (train, test)
    return data, len(eligible)
