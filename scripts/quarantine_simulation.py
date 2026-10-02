"""Measures what quarantine keeps and drops, on Aalto owners and impostors.

For each owner, the real LivePipeline (TypingScorer + TrustEngine +
Quarantine) is built from their first 10 sentences (window 100, lock
threshold 0.05, grace 3), and two streams are run through it, once for each
keep threshold (a trust value below it makes quarantine drop the records it
covers):

    owner      the owner's later sentences: what share of the owner's own
               typing is kept (the rest was in low-trust windows or near a
               false lock).
    takeover   the owner's later sentences, then straight away another
               participant's: what share of the impostor's records leaked
               into storage.

Aalto profiles are thin (~478 training records), so the owner drop rate
here is pessimistic compared with a profile built from weeks of typing.
Run from the project folder: uv run python scripts/quarantine_simulation.py [owners]
"""

import sys
import time
import zipfile

import numpy as np

from doppel.aalto import ZIP_PATH, load_sample
from doppel.app import LivePipeline
from doppel.quarantine import Quarantine
from doppel.scorer import CALIBRATION_SHARE, build_typing_scorer
from doppel.trust import TrustEngine

N_OWNERS = int(sys.argv[1]) if len(sys.argv) > 1 else 200
N_IMPOSTORS = 5
SEED = 0
SECONDS_PER_RECORD = 0.2  # spacing of the simulated clock; never a quiet period
KEEP_THRESHOLDS = [0.05, 0.1, 0.2, 0.3, 0.5]


def run_stream(train, records, keep):
    """Run records through a fresh pipeline; return the ids of records stored."""
    scorer = build_typing_scorer(train)
    stored = []
    quarantine = Quarantine(scorer.window, lambda r: stored.append(id(r)))
    pipeline = LivePipeline(scorer, TrustEngine(), quarantine, lambda: None, keep_threshold=keep)
    for i, record in enumerate(records):
        pipeline.process(record, i * SECONDS_PER_RECORD)
    quarantine.close()
    return set(stored)


start = time.perf_counter()
rng = np.random.default_rng(SEED)
z = zipfile.ZipFile(ZIP_PATH)
data, _ = load_sample(z, rng, N_OWNERS, min_test_records=100)
data = {
    p: d for p, d in data.items()
    if len(d[0]) - int(len(d[0]) * (1 - CALIBRATION_SHARE)) >= 100
}
pids = list(data)

print(f"{len(pids)} owners, {N_IMPOSTORS} impostors each; window 100, lock threshold 0.05, grace 3")
print(f"{'keep threshold':>15}{'owner kept':>14}{'impostor leaked':>18}{'streams with no leak':>23}")
impostors = {o: [p for p in pids if p != o] for o in pids}
picks = {o: rng.choice(len(impostors[o]), size=N_IMPOSTORS, replace=False) for o in pids}
for keep in KEEP_THRESHOLDS:
    owner_kept = owner_total = leaked = impostor_total = 0
    leak_per_stream = []
    for owner in pids:
        train, test = data[owner]
        kept = run_stream(train, test, keep)
        owner_kept += sum(id(r) in kept for r in test)
        owner_total += len(test)
        for i in picks[owner]:
            imp = data[impostors[owner][i]][1]
            kept = run_stream(train, test + imp, keep)
            n = sum(id(r) in kept for r in imp)
            leaked += n
            impostor_total += len(imp)
            leak_per_stream.append(n == 0)
    print(
        f"{keep:>15}{100 * owner_kept / owner_total:>13.1f}%{100 * leaked / impostor_total:>17.1f}%"
        f"{100 * np.mean(leak_per_stream):>22.0f}%"
    )
print(f"Owner keystrokes: {owner_total:_}; impostor keystrokes: {impostor_total:_}. Total time {time.perf_counter() - start:.0f} s.")
