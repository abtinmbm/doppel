"""Label experiment on the Aalto free-text dataset.

Compares ways of grouping keystroke pairs for free-text authentication, at
several window sizes: no label, keyboard-geometry label, real digraph, and
"top-K" (real digraph only for the K most common letter pairs, geometry for
the rest).
The result decides which label Doppel stores.

Data: data/aalto/Keystrokes.zip (git-ignored, read without unzipping), from
https://userinterfaces.aalto.fi/136Mkeystrokes/. Each participant typed 15
sentences in a web browser; each row is one keystroke with press and release
times in ms and the JavaScript key code (A-Z = 65-90, as on Windows).
Dhakal, Feit, Kristensson, Oulasvirta. Observations on Typing from 136 Million
Keystrokes. CHI 2018.

Method:
    1. Participants: QWERTY layout, physical keyboard (full or laptop), a
       fixed random sample. Each sentence is replayed through Doppel's own
       KeystrokeCollector (doppel.replay) with a label that keeps the key
       pair, so all schemes are computed from the same records.
    2. Time-ordered split: sentences 1-10 train the owner's profile,
       sentences 11-15 are the owner's genuine test data.
    3. Impostors: the test sentences of other sampled participants.
    4. For each scheme, a WindowScorer is fitted on the owner's training
       records. Windows of N consecutive records (every STRIDE records) are
       scored for the owner and the impostors (doppel.window_scorer: signed
       deviations summed per group), and the owner's EER computed.
    5. Reported: mean, standard deviation and median EER over owners, for
       every scheme and window size.

Run from the project folder: uv run python scripts/aalto_experiment.py [participants]
"""

import csv
import sys
from collections import Counter
import time
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd

from doppel.keymap import relation, vk_letter
from doppel.metrics import eer
from doppel.replay import replay
from doppel.window_scorer import WindowScorer, window_scores

ZIP_PATH = Path("data") / "aalto" / "Keystrokes.zip"
FILES = "Keystrokes/files/"
N_PARTICIPANTS = int(sys.argv[1]) if len(sys.argv) > 1 else 1_000
N_IMPOSTORS = 50
TRAIN_SENTENCES = 10
TEST_SENTENCES = 5
WINDOW_SIZES = [10, 25, 50, 100]
STRIDE = 5
SEED = 0
COMMON_K = [30, 100]  # sizes of the common-digraph lists

def geometry(a: int, b: int):
    """The geometry-only label: relation() for two letters, None otherwise.

    Before key kinds were added, every pair with a non-letter key shared this
    one None group. Kept here as the baseline that key kinds are compared to.
    """
    if vk_letter(a) is None or vk_letter(b) is None:
        return None
    return relation(a, b)


# Group keys for each labelling scheme, most specific first. Record labels
# here are (first key code, second key code); the tags keep the kinds of key
# apart. "geometry + kinds" is the label Doppel stores (keymap.relation).
SCHEMES = {
    "no label": lambda r: ("all",),
    "geometry": lambda r: (("geo", geometry(*r.label)), "all"),
    "digraph": lambda r: (("pair", r.label), ("geo", geometry(*r.label)), "all"),
}


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
        keystrokes = list(
            zip(s["PRESS_TIME"], s["RELEASE_TIME"], s["KEYCODE"].astype(int))
        )
        sentences.append((s["PRESS_TIME"].min(), keystrokes))
    sentences.sort(key=lambda item: item[0])  # by when the sentence started
    return [keystrokes for _, keystrokes in sentences]


def to_records(sentences):
    """Replay each sentence separately (pairs never span two sentences)."""
    records = []
    for keystrokes in sentences:
        records += replay(keystrokes, label_fn=lambda a, b: (a, b))
    return records


start = time.perf_counter()
rng = np.random.default_rng(SEED)
z = zipfile.ZipFile(ZIP_PATH)

meta = read_tsv(z, f"{FILES}metadata_participants.txt")
eligible = meta[
    (meta["LAYOUT"] == "qwerty") & meta["KEYBOARD_TYPE"].isin(["full", "laptop"])
]["PARTICIPANT_ID"].to_numpy()

# Load a random sample, keeping participants with all 15 sentences and enough
# test records for the largest window.
data = {}
for pid in rng.permutation(eligible):
    if len(data) == N_PARTICIPANTS:
        break
    try:
        sentences = load_sentences(z, int(pid))
    except (KeyError, ValueError):
        continue  # missing or unreadable file
    if len(sentences) < TRAIN_SENTENCES + TEST_SENTENCES:
        continue
    train = to_records(sentences[:TRAIN_SENTENCES])
    test = to_records(sentences[TRAIN_SENTENCES : TRAIN_SENTENCES + TEST_SENTENCES])
    if len(test) < max(WINDOW_SIZES):
        continue
    data[pid] = (train, test)

pids = list(data)
print(
    f"{len(eligible):_} eligible participants; using {len(pids)}. "
    f"Records per person: train {np.mean([len(t) for t, _ in data.values()]):.0f}, "
    f"test {np.mean([len(t) for _, t in data.values()]):.0f}. "
    f"Loaded in {time.perf_counter() - start:.0f} s."
)

# "Common digraph" schemes: only the K most frequent letter pairs keep their
# identity; every other pair is judged by its geometry label. The ranking is
# counted over all sampled participants' training records, so it describes
# the language, not any one person.
pair_counts = Counter(
    r.label
    for train, _ in data.values()
    for r in train
    if geometry(*r.label) is not None
)
for k in COMMON_K:
    common = {pair for pair, _ in pair_counts.most_common(k)}

    def common_keys(r, common=common):
        geo = ("geo", geometry(*r.label))
        if r.label in common:
            return (("pair", r.label), geo, "all")
        return (geo, "all")

    SCHEMES[f"top-{k}"] = common_keys


def with_kinds(r, letter_keys):
    """Letter pairs use letter_keys(r); other pairs use Doppel's key-kind label.

    A key-kind group with too few training records falls back to the shared
    group of all non-letter pairs, then to "all".
    """
    if geometry(*r.label) is not None:
        return letter_keys(r)
    return (("label", relation(*r.label)), ("geo", None), "all")


SCHEMES["geometry + kinds"] = lambda r: with_kinds(r, SCHEMES["geometry"])
SCHEMES["top-30 + kinds"] = lambda r: with_kinds(r, SCHEMES["top-30"])

# eers[scheme][window size] = one EER per owner
eers = {s: {n: [] for n in WINDOW_SIZES} for s in SCHEMES}
for owner in pids:
    others = [p for p in pids if p != owner]
    impostors = rng.choice(len(others), size=N_IMPOSTORS, replace=False)
    owner_train, owner_test = data[owner]
    for scheme, group_keys in SCHEMES.items():
        scorer = WindowScorer(group_keys)
        scorer.fit(owner_train)
        genuine = scorer.deviations(owner_test)
        impostor = [scorer.deviations(data[others[i]][1]) for i in impostors]
        for n in WINDOW_SIZES:
            g = window_scores(*genuine, n, STRIDE)
            imp = np.concatenate([window_scores(*dev, n, STRIDE) for dev in impostor])
            eers[scheme][n].append(eer(g, imp))

print(f"\nMean EER (std, median) over {len(pids)} owners, window = N records")
print(f"{'scheme':<17}" + "".join(f"{'N=' + str(n):>22}" for n in WINDOW_SIZES))
for scheme in SCHEMES:
    cells = []
    for n in WINDOW_SIZES:
        e = np.array(eers[scheme][n])
        cells.append(f"{e.mean():.3f} ({e.std(ddof=1):.3f}, {np.median(e):.3f})")
    print(f"{scheme:<17}" + "".join(f"{c:>22}" for c in cells))
print(f"\nTotal time {time.perf_counter() - start:.0f} s.")

# Paired comparison against geometry at the largest window: the same owners
# are scored by every scheme, so per-owner differences cancel the large
# owner-to-owner variation. 95% interval = mean +- 1.96 standard errors.
n = max(WINDOW_SIZES)
base = np.array(eers["geometry"][n])
print(f"\nEER difference vs geometry at N={n} (negative = better), 95% interval")
for scheme in SCHEMES:
    if scheme == "geometry":
        continue
    diff = np.array(eers[scheme][n]) - base
    half = 1.96 * diff.std(ddof=1) / np.sqrt(len(diff))
    print(f"{scheme:<17}{diff.mean():+.3f}  [{diff.mean() - half:+.3f}, {diff.mean() + half:+.3f}]")
