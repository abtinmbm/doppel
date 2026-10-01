"""Turns raw key events into keystroke records.

The collector receives key-down and key-up events with their timestamps and
produces one KeystrokeRecord for each pair of consecutive key presses
(k1 then k2). It does not read the clock or the keyboard itself; the caller
supplies both, so the same logic can be driven by a live listener or by a
scripted sequence of events in tests.

Keys are identified by their virtual key code (an int, see keymap.key_id),
which stays the same whether Shift, Ctrl or Caps Lock is active. This
guarantees that a key's press and its release are recognised as the same key.

How it works:
    1. `held` maps each key that is down right now to two times: when it was
       pressed, and when it was last seen (its press or its latest
       auto-repeat). A down event for a key already in `held` is an
       auto-repeat: it only updates "last seen" and produces nothing, so each
       physical press is counted once.
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

Stale keys:
    Sometimes a release is never seen, for example when the screen locks
    while a key is down. Without cleanup that key would stay in `held`
    forever and every later press of it would be ignored as an auto-repeat.
    Windows repeats the most recently pressed key about every 30 ms after an
    initial delay of about 500 ms, so a key that is really held keeps being
    seen. On every press, any held key not seen for more than stale_ms is
    dropped, together with its pending pair; if it was the previous press,
    that is forgotten too, so no pair is formed with it.

    Cost: Windows stops repeating a key once another key is pressed. A key
    held for longer than stale_ms while other keys are typed (for example
    Shift over a long capitalised phrase) is dropped too. Its own pair is
    lost and its release is ignored; all other records are unaffected.

    reset() clears all state at once. The live app calls it before locking
    the screen, since the releases of keys held at that moment will be lost.

Labels:
    A pair's label comes from label_fn(first key, second key). Doppel always
    uses the default, keymap.relation(), which returns only a coarse
    geometry label. Offline experiments on public datasets can pass another
    function (for example one returning the key pair itself) to compare
    labelling schemes.

Privacy:
    Key codes are held in memory only. A key stays in `held` and `pending`
    until it is released or dropped, and in prev_key until the next press
    replaces it. With the default label_fn, records contain only timings and
    the coarse label from keymap.relation(). A label_fn that returns key
    identities must never be used on live data.
"""

from collections.abc import Callable
from typing import Any

from doppel.keymap import relation
from doppel.records import KeystrokeRecord

# Timestamps are in nanoseconds; records are in milliseconds.
NS_PER_MS = 1_000_000

# Pairs whose presses are further apart than this are not recorded.
MAX_GAP_MS = 2000.0

# A held key not seen (pressed or auto-repeated) for longer than this is
# assumed to have been released without the release being seen. Measured
# auto-repeat: first repeat after 500.1 ms, then one every 30-47 ms.
STALE_MS = 2000.0


class KeystrokeCollector:
    """Builds KeystrokeRecords from a stream of key events."""

    def __init__(
        self,
        max_gap_ms: float = MAX_GAP_MS,
        stale_ms: float = STALE_MS,
        label_fn: Callable[[int, int], Any] = relation,
    ):
        """Start with no keys held and no previous press.

        Args:
            max_gap_ms: longest gap between two presses, in milliseconds,
                that still counts as one pair.
            stale_ms: how long a held key can go unseen, in milliseconds,
                before it is assumed released.
            label_fn: computes a pair's label from the two key codes. Live
                Doppel uses the default (keymap.relation); see "Labels".
        """
        self.max_gap_ns = max_gap_ms * NS_PER_MS
        self.stale_ns = stale_ms * NS_PER_MS
        self.label_fn = label_fn

        # Keys that are down right now: key -> (press time, last seen time), ns.
        self.held: dict[int, tuple[int, int]] = {}

        # Pairs waiting for their first key to be released:
        # first key -> (label, first key's press time, second key's press time).
        self.pending: dict[int, tuple[Any, int, int]] = {}

        # The previous press. prev_up is None while that key is still down.
        self.prev_key: int | None = None
        self.prev_down: int = 0
        self.prev_up: int | None = None

    def key_down(self, key: int, t: int) -> KeystrokeRecord | None:
        """Handle a key press at time t (ns).

        Args:
            key: virtual key code of the key.
            t: time of the event in nanoseconds.

        Returns:
            A KeystrokeRecord if this press completes a pair whose first key
            was already released, otherwise None.
        """
        # Forget keys whose release was missed, before deciding whether this
        # event is an auto-repeat. Otherwise a key whose release was lost
        # would be treated as auto-repeating forever.
        self._drop_stale(t)

        # Auto-repeat: the key is still held. Only note that it was seen.
        if key in self.held:
            down_time = self.held[key][0]
            self.held[key] = (down_time, t)
            return None

        record = None

        # This press forms a pair with the previous one, unless there is no
        # previous press or the gap between them is too long.
        if self.prev_key is not None and t - self.prev_down <= self.max_gap_ns:
            label = self.label_fn(self.prev_key, key)

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
        self.held[key] = (t, t)
        return record

    def key_up(self, key: int, t: int) -> KeystrokeRecord | None:
        """Handle a key release at time t (ns).

        Args:
            key: virtual key code of the key.
            t: time of the event in nanoseconds.

        Returns:
            A KeystrokeRecord if a pair was waiting on this key's release,
            otherwise None.
        """
        # A key that was down before the collector started, or was dropped as
        # stale, has no press time, so its release is ignored.
        entry = self.held.pop(key, None)
        if entry is None:
            return None

        # If this is the most recent press, remember when it was released so
        # the next press can complete its pair immediately.
        if key == self.prev_key:
            self.prev_up = t

        # If a later press overlapped this key, its pair can now be finished.
        waiting = self.pending.pop(key, None)
        if waiting is None:
            return None

        label, k1_down, k2_down = waiting
        return self._make_record(label, k1_down, t, k2_down)

    def reset(self) -> None:
        """Forget every held key, waiting pair and the previous press.

        Called before the screen is locked: releases that happen while it is
        locked are not seen, so the current state would become stale.
        """
        self.held.clear()
        self.pending.clear()
        self.prev_key = None
        self.prev_down = 0
        self.prev_up = None

    def _drop_stale(self, t: int) -> None:
        """Drop held keys not seen for longer than stale_ns before time t."""
        # list() makes a copy of the keys, because entries are deleted from
        # held inside the loop.
        for key in list(self.held):
            last_seen = self.held[key][1]
            if t - last_seen > self.stale_ns:
                del self.held[key]
                # Its waiting pair can never be finished.
                self.pending.pop(key, None)
                # Its release will never be seen, so no pair can use it.
                if key == self.prev_key:
                    self.prev_key = None
                    self.prev_up = None

    def _make_record(
        self, label: Any, k1_down: int, k1_up: int, k2_down: int
    ) -> KeystrokeRecord:
        """Build a record from the three event times of a pair (all in ns)."""
        hold_ms = (k1_up - k1_down) / NS_PER_MS
        dd_ms = (k2_down - k1_down) / NS_PER_MS
        ud_ms = (k2_down - k1_up) / NS_PER_MS
        return KeystrokeRecord(label, hold_ms, dd_ms, ud_ms)
