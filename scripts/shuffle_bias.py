"""Does shuffling stored batches bias calibration and offline tuning?

Doppel shuffles each 200-record batch before storing it, so every window
built from stored data (the app's calibration windows, offline tuning) is a
random mix of a batch, while live windows are contiguous typing. Contiguous
typing has streaks (same text, same mood), so its window scores may vary more,
which would make live owner trust lower than the calibration promises.

Aalto keeps true typing order, so it can measure this. Per owner (train =
sentences 1-10, test = 11-15), the owner's own test typing is scored three ways:

    C/C  contiguous calibration, contiguous test   (earlier Aalto simulations)
    S/S  shuffled calibration,   shuffled test     (offline tuning on stored data)
    S/C  shuffled calibration,   contiguous test   (what the live app sees)

"Shuffled" = shuffled within consecutive blocks of 200, as storage.py does.
Reported: share of owner trust values below 0.05 and 0.02 (a calibrated
p-value should give about 5% and 2%), and false locks per 1,000 owner
keystrokes at threshold 0.05, grace 3. If S/C is clearly worse than S/S,
tuning on stored data underestimates live false locks.

Run from the project folder: uv run python scripts/shuffle_bias.py [owners]
"""

import sys
import time
import zipfile

import numpy as np

from doppel.aalto import ZIP_PATH, load_sample
from doppel.scorer import CALIBRATION_SHARE, build_typing_scorer, calibrated_trust
from doppel.trust import TrustEngine
from doppel.window_scorer import window_scores

N_OWNERS = int(sys.argv[1]) if len(sys.argv) > 1 else 300
WINDOW, STRIDE, BATCH = 100, 10, 200
SEED = 0


def shuffle_in_blocks(records, size, rng):
    """Shuffle within consecutive blocks of `size`, keeping block order (as stored)."""
    out = []
    for i in range(0, len(records), size):
        block = list(records[i : i + size])
        rng.shuffle(block)
        out += block
    return out


def owner_trust(scorer, test):
    """Trust values for the owner's test stream (window every STRIDE records)."""
    z, groups = scorer.profile.deviations(test)
    return [calibrated_trust(s, scorer.calibration) for s in window_scores(z, groups, WINDOW, STRIDE)]


def false_locks(values, threshold=0.05, grace=3):
    """Locks in the owner's stream; engine and window reset after each."""
    engine, count, skip = TrustEngine(threshold, grace), 0, 0
    for i, trust in enumerate(values):
        if i < skip:
            continue  # window refilling after a lock (WINDOW / STRIDE values)
        if engine.update("typing", trust, i):
            count, skip = count + 1, i + WINDOW // STRIDE
            engine.reset()
    return count


# The block shuffle keeps each block's records, only reorders them.
_rng = np.random.default_rng(1)
_demo = list(range(450))
_mixed = shuffle_in_blocks(_demo, 200, _rng)
assert [sorted(_mixed[i : i + 200]) for i in (0, 200, 400)] == [_demo[0:200], _demo[200:400], _demo[400:]]
assert _mixed != _demo

start = time.perf_counter()
rng = np.random.default_rng(SEED)
data, n_eligible = load_sample(zipfile.ZipFile(ZIP_PATH), rng, N_OWNERS, min_test_records=WINDOW)
data = {p: d for p, d in data.items() if len(d[0]) - int(len(d[0]) * (1 - CALIBRATION_SHARE)) >= WINDOW}
print(f"{len(data)} owners from {n_eligible:_} eligible; loaded in {time.perf_counter() - start:.0f} s")

values = {"C/C": [], "S/S": [], "S/C": []}
low_diff = []  # per owner: share of S/C values < 0.05 minus share of S/S values
locks = dict.fromkeys(values, 0)
keystrokes = 0
for train, test in data.values():
    contiguous = build_typing_scorer(train, WINDOW, STRIDE)
    shuffled = build_typing_scorer(shuffle_in_blocks(train, BATCH, rng), WINDOW, STRIDE)
    runs = {
        "C/C": owner_trust(contiguous, test),
        "S/S": owner_trust(shuffled, shuffle_in_blocks(test, BATCH, rng)),
        "S/C": owner_trust(shuffled, test),
    }
    for name, v in runs.items():
        values[name] += v
        locks[name] += false_locks(v)
    keystrokes += len(test)
    low_diff.append(np.mean(np.array(runs["S/C"]) < 0.05) - np.mean(np.array(runs["S/S"]) < 0.05))

print(f"{keystrokes:_} owner test keystrokes\n")
print(f"{'':6}{'n values':>10}{'< 0.05':>9}{'< 0.02':>9}{'false locks / 1,000':>22}")
for name, v in values.items():
    v = np.array(v)
    print(
        f"{name:6}{len(v):>10_}{100 * np.mean(v < 0.05):>8.1f}%{100 * np.mean(v < 0.02):>8.1f}%"
        f"{1000 * locks[name] / keystrokes:>22.2f}"
    )
# Paired over owners: normal-approximation 95% interval of the mean difference.
d = np.array(low_diff)
half = 1.96 * d.std(ddof=1) / np.sqrt(len(d))
print(
    f"\nS/C - S/S, share < 0.05, mean over owners: {100 * d.mean():+.1f} pp "
    f"[{100 * (d.mean() - half):+.1f}, {100 * (d.mean() + half):+.1f}]"
)
print(f"\nTotal time {time.perf_counter() - start:.0f} s.")
