"""Checks for doppel.scorer on values worked out by hand.

Profile used below (same five records as window_scorer_test.py), all with the
label (True, 1): medians hold 100, DD 200, UD 90; every MAD is 10.
"""

import numpy as np

from doppel.records import KeystrokeRecord
from doppel.scorer import TypingScorer, build_typing_scorer, calibrated_trust, label_groups
from doppel.window_scorer import WindowScorer

G = (True, 1)


def rec(hold, dd, label=G):
    """Build a record with UD = DD - hold."""
    return KeystrokeRecord(label, float(hold), float(dd), float(dd - hold))


# Group keys: key-kind labels fall back to "nonletter", then "all".
assert label_groups(rec(1, 2, ("space", "left"))) == (("space", "left"), "nonletter", "all")
assert label_groups(rec(1, 2)) == (G, "all")

# Calibration [1, 2, 3, 4]: trust = (scores >= s, + 1) / 5.
cal = np.array([1.0, 2.0, 3.0, 4.0])
assert calibrated_trust(2.5, cal) == 3 / 5  # 3 and 4 are >= 2.5
assert calibrated_trust(2.0, cal) == 4 / 5  # a tie counts: 2, 3, 4
assert calibrated_trust(0.5, cal) == 5 / 5  # less anomalous than all of them
assert calibrated_trust(5.0, cal) == 1 / 5  # more anomalous than all of them

# Rolling window of 3, a trust value every 2 records once full.
profile = WindowScorer(label_groups, min_count=5)
profile.fit([rec(80, 200), rec(90, 180), rec(100, 220), rec(110, 190), rec(120, 210)])
scorer = TypingScorer(profile, [0.5, 1.0, 2.0, 4.0], window=3, stride=2)
# z rows: (120, 230) -> [2, 3, 2]; (100, 200) -> [0, 0, 1];
#         (80, 170) -> [-2, -3, 0]; (130, 240) -> [3, 4, 2].
# Record 3: window 1-3 sums to [0, 0, 3] -> score 3/3 = 1.0 -> 1.0, 2.0, 4.0
#           are >= 1.0 -> trust (3 + 1) / 5 = 0.8.
# Record 5: window 3-5 = [-2,-3,0] + [0,0,1] + [3,4,2] = [1, 1, 3] -> 5/3
#           -> only 2.0 and 4.0 are >= 1.67 -> trust (2 + 1) / 5 = 0.6.
out = [scorer.observe(r) for r in [rec(120, 230), rec(100, 200), rec(80, 170), rec(100, 200), rec(130, 240)]]
assert out[0] is None and out[1] is None and out[3] is None, out
assert np.isclose(out[2], 0.8) and np.isclose(out[4], 0.6), out

# reset() empties the window: the next record gives nothing.
scorer.reset()
assert scorer.observe(rec(100, 200)) is None

# build_typing_scorer: 10 records, 30% held out -> 7 train, 3 calibrate.
# Training holds 80, 90, 100, 110, 120, 100, 100 (DD likewise): medians
# hold 100, DD 200, UD 100; all MADs 10. The held-out window (120, 230),
# (100, 200), (80, 170) has z rows [2, 3, 1], [0, 0, 0], [-2, -3, -1], which
# sum to 0 -> one calibration score of 0.
train = [rec(80, 200), rec(90, 180), rec(100, 220), rec(110, 190), rec(120, 210), rec(100, 200), rec(100, 200)]
built = build_typing_scorer(train + [rec(120, 230), rec(100, 200), rec(80, 170)], window=3, stride=1)
assert np.allclose(built.profile.median[G], [100, 200, 100])
assert np.allclose(built.calibration, [0.0])

# Calibration uses a window at every position, whatever the emission stride.
# 11 records -> 7 train, 4 held out: z rows [2, 3, 1], [0, 0, 0],
# [-2, -3, -1], [0, 0, 0]. Windows of 3 at positions 0 and 1 sum to 0 and to
# [-2, -3, -1] -> scores 0 and 6/3 = 2, even with stride 10.
built = build_typing_scorer(train + [rec(120, 230), rec(100, 200), rec(80, 170), rec(100, 200)], window=3, stride=10)
assert np.allclose(built.calibration, [0.0, 2.0])
assert built.stride == 10

# Too few held-out records for one window fails loudly.
try:
    build_typing_scorer(train, window=5, stride=1)  # 7 records -> 4 train, 3 held out
    raise AssertionError("a calibration part shorter than a window should fail")
except ValueError:
    pass

print("All scorer checks passed.")
