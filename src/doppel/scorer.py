"""Scorers: each signal turns its evidence into a trust value from 0 to 1.

Doppel's trust score is a plug-in system. Every signal (typing now; mouse
later) is a scorer with the same interface: it observes its own events and,
from time to time, reports how much its latest evidence looks like the owner,
as a number from 0 (not the owner) to 1 (the owner). The trust engine fuses
whatever scorers have reported; it never needs to know how a signal works.

How the typing scorer works:
    1. It keeps the last `window` keystroke records in a rolling buffer.
    2. Every `stride` records, once the buffer is full, it scores the window
       with a WindowScorer (signed deviations summed per group).
    3. That raw score has no fixed scale, so it is calibrated against the
       owner's own typing: windows of held-out owner records, scored the same
       way when the scorer is built. The trust value is the share of those
       calibration windows that scored at least as high (as anomalous):

           trust = (number of calibration scores >= s + 1) / (count + 1)

       A window typical of the owner gets about 0.5; one more anomalous
       than all of the owner's calibration windows gets 1 / (count + 1). The
       +1 keeps trust from being exactly 0 or claiming more certainty than a
       finite calibration set allows. This is an empirical p-value.
    4. Calibrating every scorer this way puts all signals on the same scale,
       so fusing them is meaningful.

Building a typing scorer from the owner's records (build_typing_scorer):
    the earlier part trains the per-group profile, the later part
    (calibration_share) provides the calibration windows: a time-ordered
    split, so calibration reflects how the profile holds up on new typing.
    Calibration uses a window at every position (stride 1): overlapping
    windows are fine for estimating the spread of the owner's scores, and
    more of them make small trust values reachable (the smallest possible
    trust is 1 / (number of calibration windows + 1)).
"""

from collections import deque
from collections.abc import Hashable, Sequence
from typing import Protocol

import numpy as np

from doppel.records import KeystrokeRecord
from doppel.window_scorer import CLIP, WindowScorer, window_scores

# Defaults for the typing scorer.
WINDOW = 100
STRIDE = 10
CALIBRATION_SHARE = 0.3


class Scorer(Protocol):
    """What every signal provides to the trust engine."""

    name: str

    def observe(self, record: KeystrokeRecord) -> float | None:
        """Take one event; return a new trust value (0-1) when one is ready."""
        ...


def label_groups(record: KeystrokeRecord) -> tuple[Hashable, ...]:
    """Group keys for a stored label, most specific first.

    A key-kind pair whose group is too small falls back to the group of all
    pairs with a non-letter key, then to "all"; a letter pair falls back to
    "all". This is the grouping measured as "geometry + kinds" on Aalto.
    """
    if isinstance(record.label[0], str):  # key kinds, e.g. ("space", "left")
        return (record.label, "nonletter", "all")
    return (record.label, "all")


def calibrated_trust(score: float, calibration: np.ndarray) -> float:
    """Share of the owner's calibration scores at least as high as `score`.

    Args:
        score: a window's anomaly score.
        calibration: the owner's calibration window scores, sorted ascending.

    Returns:
        (count of calibration scores >= score + 1) / (len(calibration) + 1).
    """
    # searchsorted finds how many calibration scores are below `score`.
    at_least = len(calibration) - int(np.searchsorted(calibration, score, side="left"))
    return (at_least + 1) / (len(calibration) + 1)


class TypingScorer:
    """Turns a stream of keystroke records into calibrated trust values."""

    name = "typing"

    def __init__(
        self,
        profile: WindowScorer,
        calibration: Sequence[float],
        window: int = WINDOW,
        stride: int = STRIDE,
    ):
        """Set up the rolling window.

        Args:
            profile: a fitted WindowScorer for the owner.
            calibration: the owner's held-out window scores.
            window: records per window (N).
            stride: records between two trust values.
        """
        self.profile = profile
        self.calibration = np.sort(np.asarray(calibration, dtype=float))
        self.window = window
        self.stride = stride
        self.buffer: deque[KeystrokeRecord] = deque(maxlen=window)
        self.seen = 0

    def observe(self, record: KeystrokeRecord) -> float | None:
        """Add a record; every `stride` records with a full window, return trust."""
        self.buffer.append(record)  # the oldest record drops out when full
        self.seen += 1
        full = len(self.buffer) == self.window
        if not full or (self.seen - self.window) % self.stride != 0:
            return None
        z, groups = self.profile.deviations(list(self.buffer))
        score = float(window_scores(z, groups, self.window, self.window)[0])
        return calibrated_trust(score, self.calibration)

    def reset(self) -> None:
        """Forget the buffered records (e.g. after a lock)."""
        self.buffer.clear()
        self.seen = 0


def build_typing_scorer(
    records: Sequence[KeystrokeRecord],
    window: int = WINDOW,
    stride: int = STRIDE,
    calibration_share: float = CALIBRATION_SHARE,
    min_count: int = 5,
    kind: str = "log2",
    clip: float | None = CLIP,
) -> TypingScorer:
    """Build a typing scorer from the owner's records, in typing order.

    The first (1 - calibration_share) of the records train the profile; the
    rest are scored in windows (one at every position) to calibrate it.
    kind and clip choose the window scorer's features and cap (see
    window_scorer.py); the defaults are the measured best.

    Raises:
        ValueError: if the calibration part is shorter than one window.
    """
    cut = int(len(records) * (1 - calibration_share))
    train, held_out = records[:cut], records[cut:]
    # Check the input before any work, so a too-small dataset fails with a
    # clear message instead of an error from deep inside the fitting.
    if len(held_out) < window:
        raise ValueError(f"need at least {window} calibration records, got {len(held_out)}")
    profile = WindowScorer(label_groups, min_count, kind, clip)
    profile.fit(train)
    z, groups = profile.deviations(held_out)
    calibration = window_scores(z, groups, window, 1)  # every window position
    return TypingScorer(profile, calibration, window, stride)
