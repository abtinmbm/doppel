"""Checks for doppel.collector.KeystrokeCollector.

Each check replays a scripted sequence of key events through a fresh
collector and compares the records it produces with values worked out by
hand. Times in the scripts are in milliseconds and are converted to
nanoseconds, the unit the collector expects.
"""

from pynput.keyboard import KeyCode

from doppel.collector import KeystrokeCollector
from doppel.records import KeystrokeRecord

# One key object per letter, reused so every event refers to the same key.
T = KeyCode.from_char("t")
H = KeyCode.from_char("h")
E = KeyCode.from_char("e")
L = KeyCode.from_char("l")


def run(events):
    """Feed (action, key, time_ms) events to a new collector.

    Returns the list of records produced, in the order they came out.
    """
    collector = KeystrokeCollector()
    records = []
    for action, key, time_ms in events:
        t = time_ms * 1_000_000
        if action == "down":
            record = collector.key_down(key, t)
        else:
            record = collector.key_up(key, t)
        if record is not None:
            records.append(record)
    return records


# No overlap: t is released before h goes down, so the record comes out
# when h goes down.
records = run(
    [
        ("down", T, 0),
        ("up", T, 80),
        ("down", H, 130),
    ]
)
assert records == [KeystrokeRecord((False, 2), 80.0, 130.0, 50.0)], records

# Three keys overlapping (fast "the"). Each record comes out when its first
# key is released, so h->e comes out before t->h.
records = run(
    [
        ("down", T, 0),
        ("down", H, 35),
        ("down", E, 44),
        ("up", H, 114),
        ("up", T, 122),
        ("up", E, 191),
    ]
)
assert records == [
    KeystrokeRecord((False, 2), 79.0, 9.0, -70.0),  # h -> e
    KeystrokeRecord((False, 2), 122.0, 35.0, -87.0),  # t -> h
], records

# Auto-repeat: the extra downs while t is held are ignored, so t counts as
# one press held for 800 ms.
records = run(
    [
        ("down", T, 0),
        ("down", T, 500),
        ("down", T, 530),
        ("up", T, 800),
        ("down", H, 900),
    ]
)
assert records == [KeystrokeRecord((False, 2), 800.0, 900.0, 100.0)], records

# Long pause: presses more than 2 seconds apart do not form a pair.
records = run(
    [
        ("down", T, 0),
        ("up", T, 80),
        ("down", H, 3000),
    ]
)
assert records == [], records

# Double letter ("ll"): two real presses of the same key form a pair.
records = run(
    [
        ("down", L, 0),
        ("up", L, 90),
        ("down", L, 200),
    ]
)
assert records == [KeystrokeRecord((True, 0), 90.0, 200.0, 110.0)], records

print("All collector checks passed.")
