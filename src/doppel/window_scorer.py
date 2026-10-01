"""Scores windows of free-text keystroke records against the owner's profile.

A single pair of key presses says almost nothing about who is typing, so
Doppel judges a window of N consecutive records. The scorer learns, for each
group of similar pairs, the owner's typical timing and how much it normally
varies. A window scores high when, within its groups, the timings are
shifted away from the owner's typical values. Low = looks like the owner.

How it works:
    1. A grouping function maps each record to a list of group keys, from
       most specific to least specific. For example, with real digraphs:
       (the key pair, its geometry label, "all").
    2. fit(): for every group key, the training records in that group give a
       median and a median absolute deviation (MAD) for each feature (hold,
       DD, UD). Medians are used because typing times are right-skewed:
       a few long pauses would drag a mean and a standard deviation upwards.
    3. A record uses the first of its group keys that had at least min_count
       training records. Rare groups fall back to broader ones, so a digraph
       the owner seldom typed is judged by its geometry group instead.
    4. deviations(): each record's signed, scaled deviation per feature,
           z = (value - median) / MAD
       using its group's statistics, plus the group it used.
    5. window_scores(): within a window of N records, the z values of each
       group are summed per feature (signed), and
           score = sum over groups and features of |sum of z| / N.
       Summing before taking the absolute value lets random noise cancel
       (the owner is sometimes slower, sometimes faster), while a consistent
       shift (an impostor who is always slower on these pairs) adds up. A
       group with one record in the window contributes its plain |z|.

The MAD is floored at MIN_MAD_MS (the 1 ms resolution of the timings), so a
group with identical training values does not cause a division by zero.
"""

from collections.abc import Callable, Hashable, Sequence

import numpy as np

from doppel.records import KeystrokeRecord

# Default minimum number of training records for a group to be used.
MIN_COUNT = 5

# Smallest MAD allowed, in milliseconds.
MIN_MAD_MS = 1.0

GroupKeys = Callable[[KeystrokeRecord], Sequence[Hashable]]


def features(records: Sequence[KeystrokeRecord]) -> np.ndarray:
    """Return the timings as an array: one row per record, columns hold, DD, UD."""
    return np.array([[r.hold_ms, r.dd_ms, r.ud_ms] for r in records], dtype=float)


class WindowScorer:
    """Per-group robust timing profile of one person."""

    def __init__(self, group_keys: GroupKeys, min_count: int = MIN_COUNT):
        """Set how records are grouped.

        Args:
            group_keys: maps a record to its group keys, most specific first.
                The last key should be shared by every record (e.g. "all")
                so that every record has a group to fall back to.
            min_count: training records a group needs before it is used.
        """
        self.group_keys = group_keys
        self.min_count = min_count

    def fit(self, records: Sequence[KeystrokeRecord]) -> None:
        """Learn the median and MAD of every group with enough training records."""
        values = features(records)

        # Rows of the training array that belong to each group key.
        rows: dict[Hashable, list[int]] = {}
        for i, record in enumerate(records):
            for key in self.group_keys(record):
                rows.setdefault(key, []).append(i)

        # Statistics only for groups with enough data.
        self.median: dict[Hashable, np.ndarray] = {}
        self.mad: dict[Hashable, np.ndarray] = {}
        for key, idx in rows.items():
            if len(idx) < self.min_count:
                continue
            group = values[idx]
            median = np.median(group, axis=0)
            self.median[key] = median
            self.mad[key] = np.maximum(
                np.median(np.abs(group - median), axis=0), MIN_MAD_MS
            )

    def deviations(
        self, records: Sequence[KeystrokeRecord]
    ) -> tuple[np.ndarray, list[Hashable]]:
        """Return each record's scaled deviations and the group it was judged by.

        Returns:
            z: array (records x features) of (value - median) / MAD.
            groups: the group key used for each record.

        Raises:
            KeyError: if a record has no group with enough training data
                (only possible if the last group key is not shared by all).
        """
        values = features(records)
        medians = np.empty_like(values)
        mads = np.empty_like(values)
        groups = []
        for i, record in enumerate(records):
            # The most specific group that has statistics.
            key = next((k for k in self.group_keys(record) if k in self.median), None)
            if key is None:
                raise KeyError(f"no group with enough training data for record {i}")
            medians[i] = self.median[key]
            mads[i] = self.mad[key]
            groups.append(key)
        return (values - medians) / mads, groups


def window_scores(
    z: np.ndarray, groups: Sequence[Hashable], size: int, stride: int
) -> np.ndarray:
    """Score sliding windows of `size` records, starting every `stride` records.

    Args:
        z: scaled deviations from WindowScorer.deviations().
        groups: group of each record, from the same call.
        size: records per window (N).
        stride: records between the starts of consecutive windows.

    Returns:
        One score per complete window: sum over groups and features of
        |sum of z in that group|, divided by size.
    """
    # Number each distinct group so that per-group sums can use an array.
    index: dict[Hashable, int] = {}
    ids = np.array([index.setdefault(g, len(index)) for g in groups], dtype=int)

    scores = []
    for start in range(0, len(z) - size + 1, stride):
        sums = np.zeros((len(index), z.shape[1]))
        # Add each record's z row to its group's row of sums.
        np.add.at(sums, ids[start : start + size], z[start : start + size])
        scores.append(np.abs(sums).sum() / size)
    return np.array(scores)
