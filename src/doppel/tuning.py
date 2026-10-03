"""Choosing the lock threshold and grace from simulated owner and impostor typing.

The lock rule has two settings: the threshold (trust below it is "low") and
grace (low values in a row needed to lock). Both are chosen by replaying
typing through a real TypingScorer and TrustEngine and counting what happens.

How it works:
    1. trust_values() scores a stream of records in one pass: one trust value
       per window, at the same positions where TypingScorer.observe() would
       emit them (window, window + stride, ...).
    2. false_locks() replays the owner's own later typing through a
       TrustEngine. Every lock is a false lock; after one, the engine resets
       and the window must refill, as after a real lock and login.
    3. first_lock() replays an impostor's typing and returns how many
       keystrokes it took to lock (None if never). With after_quiet=True the
       engine starts as if the owner had left a while ago, so the first low
       value locks.
    4. false_lock_limit() turns the owner's target (at most N false locks per
       day) into false locks per 1,000 keystrokes, using how many keystrokes
       the owner types per day.
    5. choose_setting() keeps only settings within that limit that catch at
       least one impostor, and picks the one that locks out the most; ties go to the fewer keystrokes
       to lock, then the higher threshold (the more sensitive setting).

Positions are keystroke counts (records) and are passed to the engine as its
time, so the engine's quiet-period rule never fires inside a stream; quiet
periods are simulated explicitly with after_quiet.
"""

from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np

from doppel.scorer import TypingScorer, calibrated_trust
from doppel.trust import TrustEngine
from doppel.window_scorer import window_scores


def trust_values(
    scorer: TypingScorer, z: np.ndarray, groups: Sequence
) -> list[tuple[int, float]]:
    """Trust after each window of a stream, as (window end position, trust).

    Args:
        scorer: a built TypingScorer (its window, stride and calibration are used).
        z, groups: the stream's deviations from scorer.profile.deviations().

    Returns:
        One (end, trust) pair per window, equal to what observe() would emit.
    """
    scores = window_scores(z, groups, scorer.window, scorer.stride)
    return [
        (scorer.window + i * scorer.stride, calibrated_trust(s, scorer.calibration))
        for i, s in enumerate(scores)
    ]


def false_locks(
    values: Sequence[tuple[int, float]], window: int, threshold: float, grace: int
) -> int:
    """Count locks during the owner's own typing; reset and refill after each."""
    engine = TrustEngine(threshold, grace)
    count, resume_at = 0, 0
    for end, trust in values:
        if end < resume_at:
            continue  # window still refilling after a lock
        if engine.update("typing", trust, end):
            count += 1
            engine.reset()
            resume_at = end + window
    return count


def first_lock(
    values: Sequence[tuple[int, float]],
    start: int,
    threshold: float,
    grace: int,
    after_quiet: bool,
) -> int | None:
    """Keystrokes from `start` to the first lock, or None if it never locks.

    Values whose window ends at or before `start` are skipped (they are the
    owner's typing before a takeover).
    """
    engine = TrustEngine(threshold, grace)
    if after_quiet:
        engine.update("typing", 1.0, -1_000_000)  # old evidence, long ago
    for end, trust in values:
        if end <= start:
            continue
        if engine.update("typing", trust, end):
            return end - start
    return None


def false_lock_limit(keystrokes_per_day: float, locks_per_day: float = 1.0) -> float:
    """False locks per 1,000 keystrokes allowed by a per-day target."""
    return 1000 * locks_per_day / keystrokes_per_day


@dataclass(frozen=True)
class Setting:
    """One lock setting and how it did in simulation."""

    threshold: float
    grace: int
    false_per_1000: float  # owner's false locks per 1,000 keystrokes
    caught: float  # share of impostors locked out (0-1)
    median_keys: float | None  # median keystrokes to lock among those caught


def choose_setting(settings: Sequence[Setting], limit: float) -> Setting | None:
    """Best setting with false_per_1000 <= limit, or None if none qualifies.

    A setting that catches no impostor never qualifies: a threshold below the
    smallest possible trust value has zero false locks only because it can
    never lock at all. Best = most impostors caught; then fewest keystrokes
    to lock; then the higher threshold.
    """
    allowed = [s for s in settings if s.false_per_1000 <= limit and s.caught > 0]
    if not allowed:
        return None
    return max(
        allowed,
        key=lambda s: (
            s.caught,
            -(s.median_keys if s.median_keys is not None else float("inf")),
            s.threshold,
        ),
    )
