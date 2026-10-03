"""Checks for doppel.tuning with hand-worked lock sequences.

Trust values are (window end position, trust) pairs, a value every 10
keystrokes. "low" = 0.05 and "good" = 0.5 against threshold 0.1.
"""

import numpy as np

from doppel.records import KeystrokeRecord
from doppel.scorer import build_typing_scorer
from doppel.tuning import (
    Setting,
    choose_setting,
    false_lock_limit,
    false_locks,
    first_lock,
    trust_values,
)

LOW, GOOD = 0.05, 0.5

# false_locks, window 20, grace 2: lows at 20, 30 lock at 30 (1). The window
# refills until 50, so 40 is skipped. 50 low, 60 good resets, 70 and 80 low
# lock at 80 (2). Without the skip, 40 + 50 would lock again and give 3.
owner = [(20, LOW), (30, LOW), (40, LOW), (50, LOW), (60, GOOD), (70, LOW), (80, LOW)]
assert false_locks(owner, window=20, threshold=0.1, grace=2) == 2

# Takeover at keystroke 30, grace 2: values ending at or before 30 are the
# owner's, so 30's low is ignored; 40 and 50 lock at 50 -> 50 - 30 = 20.
takeover = [(20, GOOD), (30, LOW), (40, LOW), (50, LOW)]
assert first_lock(takeover, start=30, threshold=0.1, grace=2, after_quiet=False) == 20

# After a quiet period, the first low locks even with grace 3.
assert first_lock([(20, LOW)], start=0, threshold=0.1, grace=3, after_quiet=True) == 20
# ...but a good value first restores grace, so one low no longer locks.
assert first_lock([(20, GOOD), (30, LOW)], 0, 0.1, 3, after_quiet=True) is None
# Without the quiet period, one low with grace 3 does not lock.
assert first_lock([(20, LOW)], 0, 0.1, 3, after_quiet=False) is None

# false_lock_limit: 1 per day at 2,000 keystrokes/day = 0.5 per 1,000;
# 2 per day at 5,000 = 0.4.
assert false_lock_limit(2000) == 0.5
assert false_lock_limit(5000, locks_per_day=2) == 0.4

# choose_setting.
a = Setting(0.05, 3, false_per_1000=0.8, caught=0.9, median_keys=40)
b = Setting(0.02, 3, false_per_1000=0.4, caught=0.7, median_keys=50)
c = Setting(0.02, 1, false_per_1000=0.45, caught=0.8, median_keys=20)
d = Setting(0.01, 1, false_per_1000=0.3, caught=0.8, median_keys=30)
# Limit 0.5 rules out a; c and d both catch 80%, c locks faster (20 < 30).
assert choose_setting([a, b, c, d], limit=0.5) == c
assert choose_setting([a, b, c, d], limit=1.0) == a  # a allowed, catches most
assert choose_setting([a, b, c, d], limit=0.2) is None  # nothing meets it
# Same catch rate and speed: the higher threshold wins.
e = Setting(0.05, 2, false_per_1000=0.1, caught=0.8, median_keys=20)
assert choose_setting([c, e], limit=0.5) == e
# A setting that catches nobody never qualifies, even with zero false locks
# (a threshold below the smallest possible trust can never lock).
f = Setting(0.001, 1, false_per_1000=0.0, caught=0.0, median_keys=None)
assert choose_setting([f, b], limit=0.5) == b
assert choose_setting([f], limit=0.5) is None

# trust_values gives exactly what TypingScorer.observe() emits on the same
# stream (synthetic owner: one label, timings around 100 / 150 ms).
rng = np.random.default_rng(0)


def fake(n, hold, dd):
    """n records with one geometry label and noisy timings."""
    return [
        KeystrokeRecord((True, 1), float(h), float(t), float(t - h))
        for h, t in zip(rng.normal(hold, 10, n), rng.normal(dd, 20, n))
    ]


scorer = build_typing_scorer(fake(200, 100, 150), window=20, stride=5)
stream = fake(60, 110, 170)
z, groups = scorer.profile.deviations(stream)
one_pass = trust_values(scorer, z, groups)
live = [(i + 1, v) for i, r in enumerate(stream) if (v := scorer.observe(r)) is not None]
assert [end for end, _ in one_pass] == [end for end, _ in live] == list(range(20, 61, 5))
assert np.allclose([t for _, t in one_pass], [t for _, t in live])

print("All tuning checks passed.")
