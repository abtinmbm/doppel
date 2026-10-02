"""Quarantine: only typing that was judged to be the owner's is stored.

The live app scores typing in sliding windows. Without a gate, every record
would be stored and later used to train the owner's profile, including
records typed by someone else before the screen locked. That would keep
their data (a privacy problem) and let someone slowly poison the profile
just by using the computer. Quarantine holds each record back until the
scorer has finished judging it.

How it works:
    1. add(): a new record enters quarantine.
    2. judge(low): each time the scorer emits a trust value, it covers the
       last `window` records. Every record still in quarantine within that
       range counts one more judgment, and is flagged if the value was low.
    3. A record leaves the scoring window once `window` newer records have
       arrived; it can never be judged again, so its fate is decided then:
       released (stored) if it was judged at least once and never flagged,
       otherwise dropped (never written anywhere).
    4. drop_all(): on a lock, everything still in quarantine is dropped:
       those are the keystrokes that caused it.
    5. close(): on shutdown, records already judged and never flagged are
       released; records never judged are dropped.

Example with window 3: records 1-3 arrive and a good value is emitted (all
three judged once). Record 4 arrives, so record 1 leaves the window: judged,
not flagged, released. A low value then flags records 2-4, so each is
dropped as it leaves.

Cost: the owner's own records in a window that looked unusual are dropped
too, so the profile can slowly narrow toward the owner's most typical
typing. The share dropped is measured in scripts/quarantine_simulation.py.
"""

from collections import deque
from collections.abc import Callable

from doppel.records import KeystrokeRecord


class Quarantine:
    """Holds records until the scorer has judged them; releases only clean ones."""

    def __init__(self, window: int, release: Callable[[KeystrokeRecord], None]):
        """Set the window size and where released records go.

        Args:
            window: records covered by one trust value (the scorer's window).
            release: called with each record that passes (e.g. the storage
                writer's submit).
        """
        self.window = window
        self.release = release
        # Each entry: [index, record, times judged, flagged].
        self.pending: deque[list] = deque()
        self.count = 0
        self.kept = 0
        self.dropped = 0

    def add(self, record: KeystrokeRecord) -> None:
        """Put a new record in quarantine; decide on any record that left the window."""
        self.count += 1
        self.pending.append([self.count, record, 0, False])
        # A record is out of the window once `window` newer records exist.
        while self.pending and self.count - self.pending[0][0] >= self.window:
            self._decide(self.pending.popleft())

    def judge(self, low: bool) -> None:
        """Record one trust value covering the last `window` records."""
        oldest_covered = self.count - self.window + 1
        for entry in reversed(self.pending):  # newest first; stop at the window's start
            if entry[0] < oldest_covered:
                break
            entry[2] += 1
            entry[3] = entry[3] or low

    def drop_all(self) -> None:
        """Drop everything still in quarantine (after a lock)."""
        self.dropped += len(self.pending)
        self.pending.clear()

    def close(self) -> None:
        """Release judged, unflagged records; drop the rest (at shutdown)."""
        while self.pending:
            self._decide(self.pending.popleft())

    def _decide(self, entry: list) -> None:
        """Release a record judged at least once and never flagged; drop it otherwise."""
        _index, record, judged, flagged = entry
        if judged > 0 and not flagged:
            self.release(record)
            self.kept += 1
        else:
            self.dropped += 1
