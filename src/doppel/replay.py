"""Replays recorded keystrokes from a dataset through a KeystrokeCollector.

Public datasets such as Aalto store one row per keystroke: its press time,
release time and key code. Doppel's collector instead expects a stream of
separate down and up events in time order, the way a live keyboard hook
delivers them. replay() converts the first into the second, so datasets are
turned into records by exactly the same code that runs live.

How it works:
    1. Each keystroke (press_ms, release_ms, key_code) becomes two events: a
       down at press_ms and an up at release_ms. Keystrokes whose release is
       before their press are invalid and skipped.
    2. All events are sorted by time. When an up and a down happen in the same
       millisecond, the up is processed first, so the pair counts as touching
       (UD = 0) rather than overlapping.
    3. The events are fed to a fresh collector (milliseconds converted to
       nanoseconds), and every record it produces is collected.
"""

from collections.abc import Callable, Iterable
from typing import Any

from doppel.collector import NS_PER_MS, KeystrokeCollector
from doppel.keymap import relation
from doppel.records import KeystrokeRecord

# Sort order for events in the same millisecond: releases before presses.
_UP, _DOWN = 0, 1


def replay(
    keystrokes: Iterable[tuple[float, float, int]],
    label_fn: Callable[[int, int], Any] = relation,
) -> list[KeystrokeRecord]:
    """Turn (press_ms, release_ms, key_code) keystrokes into KeystrokeRecords.

    Args:
        keystrokes: one tuple per key press, in any order.
        label_fn: passed to the collector to label each pair.

    Returns:
        The records in the order the collector produced them.
    """
    events = []
    for press_ms, release_ms, key_code in keystrokes:
        if release_ms < press_ms:
            continue
        events.append((press_ms, _DOWN, key_code))
        events.append((release_ms, _UP, key_code))
    events.sort()

    collector = KeystrokeCollector(label_fn=label_fn)
    records = []
    for time_ms, kind, key_code in events:
        t = int(time_ms * NS_PER_MS)
        if kind == _DOWN:
            record = collector.key_down(key_code, t)
        else:
            record = collector.key_up(key_code, t)
        if record is not None:
            records.append(record)
    return records
