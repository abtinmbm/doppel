"""Checks for doppel.detectors on a two-feature example worked out by hand.

Training samples [1, 10] and [3, 30]:
    mean   = [2, 20]
    spread = mean absolute deviation = [(1 + 1) / 2, (10 + 10) / 2] = [1, 10]
Test sample [5, 24] differs from the mean by [3, 4]:
    Euclidean        sqrt(3^2 + 4^2)  = 5
    Manhattan        3 + 4            = 7
    Scaled Manhattan 3 / 1 + 4 / 10   = 3.4
The training mean itself scores 0 with every detector.
"""

import numpy as np

from doppel.detectors import (
    EuclideanDetector,
    ManhattanDetector,
    ScaledManhattanDetector,
)

train = [[1, 10], [3, 30]]
samples = [[5, 24], [2, 20]]

for detector, expected in [
    (EuclideanDetector(), [5.0, 0.0]),
    (ManhattanDetector(), [7.0, 0.0]),
    (ScaledManhattanDetector(), [3.4, 0.0]),
]:
    detector.fit(train)
    scores = detector.score(samples)
    assert np.allclose(scores, expected), (type(detector).__name__, scores)

# The scaled detector learned the per-feature spread.
scaled = ScaledManhattanDetector()
scaled.fit(train)
assert np.allclose(scaled.spread, [1.0, 10.0])

# A feature with no spread in training does not cause a division by zero.
flat = ScaledManhattanDetector()
flat.fit([[1, 5], [3, 5]])
assert np.all(np.isfinite(flat.score([[2, 5]])))

print("All detector checks passed.")
