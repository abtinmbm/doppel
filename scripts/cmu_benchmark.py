"""Reproduces Killourhy & Maxion (2009) on the CMU keystroke benchmark.

Validates Doppel's evaluation code (doppel.metrics, doppel.detectors): if the
mean EERs match the paper's, the code that computes them is correct.

Data: data/cmu/DSL-StrongPasswordData.csv (git-ignored), from
https://www.cs.cmu.edu/~keystroke/. 51 subjects each typed ".tie5Roanl"
400 times in 8 sessions of 50. Each row has subject, sessionIndex, rep and
31 timing features (11 hold, 10 down-down, 10 up-down), in seconds.

Evaluation method (the paper's), repeated with each subject as the owner:
    train    = the owner's first 200 repetitions (sessions 1-4)
    genuine  = the owner's last 200 repetitions (sessions 5-8)
    impostor = the first 5 repetitions of each of the other 50 subjects
The detector is fitted on the training rows only, the EER is computed from
the genuine and impostor scores, and the mean and standard deviation of the
51 EERs are reported.

Run from the project folder: uv run python scripts/cmu_benchmark.py
"""

from pathlib import Path

import numpy as np
import pandas as pd

from doppel.detectors import (
    EuclideanDetector,
    ManhattanDetector,
    ScaledManhattanDetector,
)
from doppel.metrics import eer

DATA_PATH = Path("data") / "cmu" / "DSL-StrongPasswordData.csv"
TRAIN_REPS = 200
IMPOSTOR_REPS = 5

data = pd.read_csv(DATA_PATH)
# Rows in typing order within each subject, so "first 200" means sessions 1-4.
data = data.sort_values(["subject", "sessionIndex", "rep"])
feature_columns = list(data.columns[3:])
subjects = list(data["subject"].unique())

# Sanity checks on the file before any results are trusted.
assert len(subjects) == 51, len(subjects)
assert len(feature_columns) == 31, len(feature_columns)
assert (data.groupby("subject").size() == 400).all()

# Each subject's samples as an array (rows = repetitions, columns = features).
samples = {s: data.loc[data["subject"] == s, feature_columns].to_numpy() for s in subjects}

detectors = {
    "Euclidean": EuclideanDetector,
    "Manhattan": ManhattanDetector,
    "Scaled Manhattan": ScaledManhattanDetector,
}

# Published mean EER (standard deviation), from https://www.cs.cmu.edu/~keystroke/
PUBLISHED = {
    "Euclidean": (0.1706, 0.0952),
    "Manhattan": (0.1529, 0.0925),
    "Scaled Manhattan": (0.0962, 0.0694),
}

print(
    f"{'Detector':<18}{'mean EER':>10}{'std':>8}{'min':>8}{'median':>8}{'max':>8}"
    f"{'paper':>18}"
)
for name, make_detector in detectors.items():
    eers = []
    for owner in subjects:
        train = samples[owner][:TRAIN_REPS]
        genuine = samples[owner][TRAIN_REPS:]
        impostor = np.vstack(
            [samples[other][:IMPOSTOR_REPS] for other in subjects if other != owner]
        )

        detector = make_detector()
        detector.fit(train)
        eers.append(eer(detector.score(genuine), detector.score(impostor)))

    eers = np.array(eers)
    paper_mean, paper_std = PUBLISHED[name]
    print(
        f"{name:<18}{eers.mean():>10.4f}{eers.std(ddof=1):>8.4f}"
        f"{eers.min():>8.3f}{np.median(eers):>8.3f}{eers.max():>8.3f}"
        f"{paper_mean:>10.4f} ({paper_std:.4f})"
    )
