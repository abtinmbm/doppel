"""Distance-based anomaly detectors for keystroke timing vectors.

Each detector learns the owner's typing from training samples only (it never
sees an impostor), then gives new samples an anomaly score: how far they are
from the owner's typical typing. Low = looks like the owner.

Every detector has the same two methods, so they can be swapped freely:
    fit(train)      learn from an array of shape (samples, features)
    score(samples)  return one anomaly score per row

How it works:
    1. fit() computes the mean vector of the training samples: the owner's
       "typical" timing for every feature.
    2. score() measures how far each sample is from that mean:
       - Euclidean:        sqrt(sum((x - mean)^2)), straight-line distance.
       - Manhattan:        sum(|x - mean|), the total of the per-feature gaps.
       - Scaled Manhattan: sum(|x - mean| / spread), where spread is the
         feature's mean absolute deviation in training. A 20 ms gap counts
         more on a feature the owner types consistently than on one that
         varies a lot.

These are three of the detectors evaluated by Killourhy & Maxion (2009) on
the CMU keystroke benchmark.
"""

import numpy as np
from numpy.typing import ArrayLike

# Smallest spread allowed in the scaled detector. A feature with zero spread
# in training would otherwise cause a division by zero.
MIN_SPREAD = 1e-9


class EuclideanDetector:
    """Anomaly score = Euclidean distance from the training mean."""

    def fit(self, train: ArrayLike) -> None:
        """Learn the mean of the training samples (shape: samples x features)."""
        self.mean = np.asarray(train, dtype=float).mean(axis=0)

    def score(self, samples: ArrayLike) -> np.ndarray:
        """Return the distance of each sample (row) from the training mean."""
        diff = np.asarray(samples, dtype=float) - self.mean
        return np.sqrt(np.sum(diff**2, axis=1))


class ManhattanDetector:
    """Anomaly score = Manhattan (city-block) distance from the training mean."""

    def fit(self, train: ArrayLike) -> None:
        """Learn the mean of the training samples (shape: samples x features)."""
        self.mean = np.asarray(train, dtype=float).mean(axis=0)

    def score(self, samples: ArrayLike) -> np.ndarray:
        """Return the sum of absolute per-feature gaps for each sample (row)."""
        diff = np.asarray(samples, dtype=float) - self.mean
        return np.sum(np.abs(diff), axis=1)


class ScaledManhattanDetector:
    """Anomaly score = Manhattan distance with each feature divided by its spread."""

    def fit(self, train: ArrayLike) -> None:
        """Learn the mean and the mean absolute deviation of each feature."""
        train = np.asarray(train, dtype=float)
        self.mean = train.mean(axis=0)
        # Mean absolute deviation: the average distance of a training value
        # from the feature's mean.
        spread = np.mean(np.abs(train - self.mean), axis=0)
        self.spread = np.maximum(spread, MIN_SPREAD)

    def score(self, samples: ArrayLike) -> np.ndarray:
        """Return the sum of per-feature gaps, each divided by that feature's spread."""
        diff = np.asarray(samples, dtype=float) - self.mean
        return np.sum(np.abs(diff) / self.spread, axis=1)
