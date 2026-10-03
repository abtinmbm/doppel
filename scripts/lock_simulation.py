"""Simulates Doppel's lock decision on Aalto to choose its threshold and grace.

For each owner, a TypingScorer is built from their first 10 sentences (70%
train the profile, 30% calibrate it) and a TrustEngine decides when to lock.
Three streams are replayed through them:

    owner       the owner's own later sentences (11-15): every lock is a
                false lock. After one, the engine and window reset, as after
                a real lock and login. Reported: false locks per 1,000
                owner keystrokes.
    takeover    the owner's later sentences, then straight away another
                participant's (no pause, so grace applies; the first windows
                still contain some owner records). Reported: share of
                impostors locked out within their own test typing, and the
                median keystrokes from takeover to lock.
    after quiet another participant's typing after a quiet period, so the
                first low value locks. Same two numbers.

Every combination of window size, lock threshold and grace is reported.
The replay helpers (trust_values, false_locks, first_lock) are in doppel.tuning.
Keystroke counts are records (one per key press after the first).
Run from the project folder: uv run python scripts/lock_simulation.py [owners]
"""

import sys
import time
import zipfile

import numpy as np

from doppel.aalto import ZIP_PATH, load_sample
from doppel.scorer import CALIBRATION_SHARE, build_typing_scorer
from doppel.tuning import false_locks, first_lock, trust_values

N_OWNERS = int(sys.argv[1]) if len(sys.argv) > 1 else 500
N_IMPOSTORS = 10
WINDOWS = [50, 100]
STRIDE = 10
THRESHOLDS = [0.01, 0.02, 0.05, 0.10]
GRACES = [1, 2, 3, 5]
SEED = 0


start_time = time.perf_counter()
rng = np.random.default_rng(SEED)
z = zipfile.ZipFile(ZIP_PATH)
data, n_eligible = load_sample(z, rng, N_OWNERS, min_test_records=max(WINDOWS))
# A scorer needs at least one calibration window: the held-out 30% of the
# owner's training records must reach the largest window size.
enough = {
    p: d for p, d in data.items()
    if len(d[0]) - int(len(d[0]) * (1 - CALIBRATION_SHARE)) >= max(WINDOWS)
}
skipped = len(data) - len(enough)
data = enough
pids = list(data)
print(
    f"{len(pids)} owners from {n_eligible:_} eligible ({skipped} skipped: too little "
    f"training typing to calibrate); loaded in {time.perf_counter() - start_time:.0f} s"
)

# results[(window, threshold, grace)] -> lists of outcomes
genuine_keys = {w: 0 for w in WINDOWS}
false_count = {}
takeover = {}
quiet = {}
checked = False

for owner in pids:
    train, test = data[owner]
    others = [p for p in pids if p != owner]
    impostors = [others[i] for i in rng.choice(len(others), size=N_IMPOSTORS, replace=False)]
    for w in WINDOWS:
        scorer = build_typing_scorer(train, window=w, stride=STRIDE)
        z_own, g_own = scorer.profile.deviations(test)
        own_values = trust_values(scorer, z_own, g_own)

        # Once: the one-pass trust values equal what the live scorer emits.
        if not checked:
            live = [v for v in (scorer.observe(r) for r in test) if v is not None]
            assert np.allclose(live, [t for _, t in own_values]), "trust_values differs from observe()"
            checked = True

        genuine_keys[w] += len(test)
        imp = [scorer.profile.deviations(data[p][1]) for p in impostors]
        for th in THRESHOLDS:
            for g in GRACES:
                key = (w, th, g)
                false_count[key] = false_count.get(key, 0) + false_locks(own_values, w, th, g)
                for z_imp, g_imp in imp:
                    both = trust_values(
                        scorer, np.vstack([z_own, z_imp]), list(g_own) + list(g_imp)
                    )
                    takeover.setdefault(key, []).append(
                        first_lock(both, len(test), th, g, after_quiet=False)
                    )
            for z_imp, g_imp in imp:
                quiet.setdefault((w, th), []).append(
                    first_lock(trust_values(scorer, z_imp, g_imp), 0, th, 1, after_quiet=True)
                )


def caught(outcomes):
    """Share locked, and median keystrokes to lock among those locked."""
    hits = [k for k in outcomes if k is not None]
    median = f"{np.median(hits):.0f}" if hits else "-"
    return f"{100 * len(hits) / len(outcomes):.0f}% / {median}"


for w in WINDOWS:
    print(f"\n=== Window {w} records, a trust value every {STRIDE} records ===")
    print("False locks per 1,000 owner keystrokes (rows: threshold, columns: grace)")
    print(f"{'':>8}" + "".join(f"{'grace ' + str(g):>12}" for g in GRACES))
    for th in THRESHOLDS:
        cells = [f"{1000 * false_count[(w, th, g)] / genuine_keys[w]:.2f}" for g in GRACES]
        print(f"{th:>8}" + "".join(f"{c:>12}" for c in cells))
    print("Takeover, no pause: impostors locked out / median keystrokes to lock")
    print(f"{'':>8}" + "".join(f"{'grace ' + str(g):>12}" for g in GRACES))
    for th in THRESHOLDS:
        print(f"{th:>8}" + "".join(f"{caught(takeover[(w, th, g)]):>12}" for g in GRACES))
    print("After a quiet period (first low value locks): locked out / median keystrokes")
    for th in THRESHOLDS:
        print(f"{th:>8}{caught(quiet[(w, th)]):>12}")

print(f"\n{len(pids)} owners, {N_IMPOSTORS} impostors each; {genuine_keys[WINDOWS[0]]:_} owner keystrokes per window size.")
print(f"Total time {time.perf_counter() - start_time:.0f} s.")
