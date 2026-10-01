"""Turns raw key events into keystroke records.

The collector receives key-down and key-up events with their timestamps and
produces one KeystrokeRecord for each pair of consecutive key presses
(k1 then k2). It does not read the clock or the keyboard itself; the caller
supplies both, so the same logic can be driven by a live listener or by a
scripted sequence of events in tests.

How it works:
    1. `held` maps each key that is down right now to its press time. A
       down event for a key already in `held` is an auto-repeat and is
       ignored, so each physical press is counted once.
    2. The previous press is remembered as prev_key, prev_down and prev_up
       (prev_up is None while that key is still down).
    3. When a key goes down, it forms a pair with the previous press. The
       pair is skipped if the gap between the two presses is longer than
       max_gap_ms, because a long pause is not typing rhythm.
    4. If the previous key was already released, every time in the pair is
       known and the record is returned immediately.
    5. If the previous key is still down (the keys overlap), the label and
       both press times are stored in `pending` under the previous key. The
       record is returned when that key is released.
    6. A key can be the first key of only one pair (the next press), so each
       event produces at most one record.

Privacy:
    Keys are held in memory only. A key stays in `held` and `pending` until
    it is released, and in prev_key until the next press replaces it.
    Records contain only timings and the coarse label from keymap.relation().
"""

from doppel.keymap import relation
from doppel.records import KeystrokeRecord

# Timestamps are in nanoseconds; records are in milliseconds.
NS_PER_MS = 1_000_000

# Pairs whose presses are further apart than this are not recorded.
MAX_GAP_MS = 2000.0


class KeystrokeCollector:
    """Builds KeystrokeRecords from a stream of key events."""

    def __init__(self, max_gap_ms=MAX_GAP_MS):
        """Start with no keys held and no previous press.

        Args:
            max_gap_ms: longest gap between two presses, in milliseconds,
                that still counts as one pair.
        """
        self.max_gap_ns = max_gap_ms * NS_PER_MS

        # Keys that are down right now: key -> press time (ns).
        self.held = {}

        # Pairs waiting for their first key to be released:
        # first key -> (label, first key's press time, second key's press time).
        self.pending = {}

        # The previous press. prev_up is None while that key is still down.
        self.prev_key = None
        self.prev_down = None
        self.prev_up = None

    def key_down(self, key, t):
        """Handle a key press at time t (ns).

        Returns a KeystrokeRecord if this press completes a pair whose first
        key was already released, otherwise None.
        """
        # Auto-repeat events are ignored before any state is changed.
        if key in self.held:
            return None

        record = None

        # This press forms a pair with the previous one, unless there is no
        # previous press or the gap between them is too long.
        if self.prev_key is not None and t - self.prev_down <= self.max_gap_ns:
            label = relation(self.prev_key, key)

            if self.prev_up is not None:
                # The previous key was already released: all times are known.
                record = self._make_record(label, self.prev_down, self.prev_up, t)
            else:
                # The previous key is still down. Store the pair until it is
                # released; key_up finishes it.
                self.pending[self.prev_key] = (label, self.prev_down, t)

        # This press becomes the previous press for the next one.
        self.prev_key = key
        self.prev_down = t
        self.prev_up = None

        # held is updated last so the checks above only see earlier keys.
        self.held[key] = t
        return record

    def key_up(self, key, t):
        """Handle a key release at time t (ns).

        Returns a KeystrokeRecord if a pair was waiting on this key's
        release, otherwise None.
        """
        # A key that was already down before the collector started has no
        # press time, so its release is ignored.
        down_time = self.held.pop(key, None)
        if down_time is None:
            return None

        # If this is the most recent press, remember when it was released so
        # the next press can complete its pair immediately.
        if key == self.prev_key:
            self.prev_up = t

        # If a later press overlapped this key, its pair can now be finished.
        entry = self.pending.pop(key, None)
        if entry is None:
            return None

        label, k1_down, k2_down = entry
        return self._make_record(label, k1_down, t, k2_down)

    def _make_record(self, label, k1_down, k1_up, k2_down):
        """Build a record from the three event times of a pair (all in ns)."""
        hold_ms = (k1_up - k1_down) / NS_PER_MS
        dd_ms = (k2_down - k1_down) / NS_PER_MS
        ud_ms = (k2_down - k1_up) / NS_PER_MS
        return KeystrokeRecord(label, hold_ms, dd_ms, ud_ms)
