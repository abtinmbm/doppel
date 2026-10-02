"""Checks for doppel.window_scorer on records worked out by hand.

Most checks use the raw scale without a cap (kind="raw3", clip=None), where
the arithmetic is easy to follow; the last checks cover the default log
scale and the cap.

Five training records in group "G" (hold, DD, UD; UD = DD - hold):
    (80, 200, 120) (90, 180, 90) (100, 220, 120) (110, 190, 80) (120, 210, 90)
Sorted, the medians are hold 100, DD 200, UD 90. The absolute deviations
from them, sorted, are [0, 10, 10, 20, 20] for hold and DD and
[0, 0, 10, 30, 30] for UD, so every MAD is 10.
"""

import math

import numpy as np

from doppel.records import KeystrokeRecord
from doppel.window_scorer import WindowScorer, features, window_scores


def rec(label, hold, dd):
    """Build a record with UD = DD - hold."""
    return KeystrokeRecord(label, float(hold), float(dd), float(dd - hold))  # pyright: ignore[reportArgumentType]


def by_label(record):
    """Group keys: the record's own label, then "all"."""
    return (record.label, "all")


train = [
    rec("G", 80, 200),
    rec("G", 90, 180),
    rec("G", 100, 220),
    rec("G", 110, 190),
    rec("G", 120, 210),
]
scorer = WindowScorer(by_label, min_count=5, kind="raw3", clip=None)
scorer.fit(train)
assert np.allclose(scorer.median["G"], [100, 200, 90])
assert np.allclose(scorer.mad["G"], [10, 10, 10])

# Scaled deviations (value - median) / 10:
#   (120, 230, 110) in G -> [2, 3, 2]
#   (100, 200, 100) in G -> [0, 0, 1]
#   (80, 170, 90)   in H -> H has no training data, so it falls back to
#                           "all" (the same five records) -> [-2, -3, 0]
z, groups = scorer.deviations([rec("G", 120, 230), rec("G", 100, 200), rec("H", 80, 170)])
assert np.allclose(z, [[2, 3, 2], [0, 0, 1], [-2, -3, 0]]), z
assert groups == ["G", "G", "all"]

# One window of all three: G sums to [2, 3, 3] -> 8, "all" is [-2, -3, 0]
# -> 5. Score = (8 + 5) / 3.
assert np.allclose(window_scores(z, groups, 3, 1), [13 / 3])

# Noise cancels within a group: G records [2, 3, 2] and [-2, -3, 0] sum to
# [0, 0, 2] -> score 2 / 2 = 1, although each record alone is far off.
z2, g2 = scorer.deviations([rec("G", 120, 230), rec("G", 80, 170)])
assert np.allclose(window_scores(z2, g2, 2, 1), [1])

# Sliding windows of 2 in one group, z rows [1], [-1], [3], [1] (other
# features 0): windows give |1 - 1| / 2 = 0, |-1 + 3| / 2 = 1, |3 + 1| / 2 = 2.
z3 = np.array([[1, 0, 0], [-1, 0, 0], [3, 0, 0], [1, 0, 0]], dtype=float)
assert np.allclose(window_scores(z3, ["G"] * 4, 2, 1), [0, 1, 2])
assert np.allclose(window_scores(z3, ["G"] * 4, 2, 2), [0, 2])

# With min_count 6 no group has enough data, so scoring fails loudly.
strict = WindowScorer(by_label, min_count=6, kind="raw3", clip=None)
strict.fit(train)
try:
    strict.deviations([rec("G", 100, 200)])
    raise AssertionError("a record without a usable group should fail")
except KeyError:
    pass

# Identical training values give a MAD of 0, floored to 1 ms:
# (101, 200, 99) deviates by [1, 0, -1].
flat = WindowScorer(by_label, min_count=5, kind="raw3", clip=None)
flat.fit([rec("F", 100, 200)] * 5)
assert np.allclose(flat.deviations([rec("F", 101, 200)])[0], [[1, 0, -1]])

# The cap: with clip 3 on the raw scale, (200, 200, 0) deviates by
# (200-100)/10 = 10 -> capped to 3, (200-200)/10 = 0, (0-90)/10 = -9 -> -3.
capped = WindowScorer(by_label, min_count=5, kind="raw3", clip=3.0)
capped.fit(train)
assert np.allclose(capped.deviations([rec("G", 200, 200)])[0], [[3, 0, -3]])

# Default log scale: features are log(hold + 1) and log(DD + 1).
# (99, 199) -> [ln 100, ln 200] = [4.6052, 5.2983].
assert np.allclose(features([rec("G", 99, 199)]), [[math.log(100), math.log(200)]])

# Proportional differences: on the log scale, a record twice as slow as the
# median in both features gets the same deviation on both. Training holds
# 9, 9, 9, 99, 99 and DDs 99, 99, 99, 999, 999 (+1 gives 10/100 and 100/1000):
# median log(10) and log(100); MADs 0 -> floored at 0.01. A record (19, 199)
# is twice the median + 1 in both: deviation ln 2 / 0.01 = 69.3 -> capped at 3.
log_scorer = WindowScorer(by_label, min_count=5)
log_scorer.fit([rec("L", 9, 99)] * 3 + [rec("L", 99, 999)] * 2)
assert np.allclose(log_scorer.median["L"], [math.log(10), math.log(100)])
assert np.allclose(log_scorer.deviations([rec("L", 19, 199)])[0], [[3, 3]])

print("All window scorer checks passed.")
