"""Checks for doppel.collector.KeystrokeCollector.

Each check replays a scripted sequence of key events through a collector and
compares the records it produces with values worked out by hand. Keys are
Windows virtual key codes, as keymap.key_id() gives them. Times in the
scripts are in milliseconds and are converted to nanoseconds, the unit the
collector expects.
"""

from doppel.collector import KeystrokeCollector
from doppel.records import KeystrokeRecord

# Virtual key codes. Letter keys use the ASCII code of the uppercase letter.
T = ord("T")
H = ord("H")
E = ord("E")
L = ord("L")
A = ord("A")
B = ord("B")
I = ord("I")  # noqa: E741
SHIFT = 0xA0  # left Shift


def feed(collector, events):
    """Feed (action, key, time_ms) events to a collector.

    Returns the list of records produced, in the order they came out.
    """
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


def run(events):
    """Feed events to a new collector with default settings."""
    return feed(KeystrokeCollector(), events)


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

# Shift released before the letter (typing "A" then "b"). pynput reports
# this letter as "A" on press and "a" on release; with key codes both events
# are the same key, so nothing gets stuck.
#   Shift -> a: overlap, finished when Shift is released at 150:
#               hold 150, dd 100, ud 100 - 150 = -50. Label None (Shift).
#   a -> b:     a (0.25, 1) to b (4.75, 2) is 4.61 key widths: far;
#               both on the left half. hold 180 - 100 = 80, dd 300 - 100 = 200,
#               ud 300 - 180 = 120.
collector = KeystrokeCollector()
records = feed(
    collector,
    [
        ("down", SHIFT, 0),
        ("down", A, 100),
        ("up", SHIFT, 150),
        ("up", A, 180),
        ("down", B, 300),
        ("up", B, 380),
    ],
)
assert records == [
    KeystrokeRecord(None, 150.0, 100.0, -50.0),  # Shift -> a
    KeystrokeRecord((True, 3), 80.0, 200.0, 120.0),  # a -> b
], records
assert collector.held == {} and collector.pending == {}

# Lost release: e goes down and its release is never seen (as if the screen
# locked). At 3000 ms it has not been seen for more than 2000 ms, so it is
# dropped. Its next press at 3200 is a real press, not an auto-repeat.
#   h -> e: h (5.25, 1) to e (2, 0) is 3.40 key widths: near; different
#           halves. hold 3080 - 3000 = 80, dd 200, ud 3200 - 3080 = 120.
collector = KeystrokeCollector()
records = feed(collector, [("down", E, 0), ("down", H, 3000)])
assert E not in collector.held
assert collector.prev_key == H
records += feed(
    collector,
    [
        ("up", H, 3080),
        ("down", E, 3200),
        ("up", E, 3290),
    ],
)
assert records == [KeystrokeRecord((False, 2), 80.0, 200.0, 120.0)], records
assert collector.held == {} and collector.pending == {}

# Long genuine hold: t is held for 3010 ms and auto-repeats every 31 ms after
# a 500 ms delay, so it is never unseen for 2000 ms and is not dropped. The
# max gap is raised to 5000 ms so that t and h still form a pair. One record
# with the full hold shows no repeat was counted as a new press.
#   t -> h: hold 3010, dd 3100, ud 3100 - 3010 = 90.
repeats = [("down", T, 500 + 31 * i) for i in range(81)]  # 500 ... 2980
records = feed(
    KeystrokeCollector(max_gap_ms=5000.0),
    [("down", T, 0)] + repeats + [("up", T, 3010), ("down", H, 3100)],
)
assert records == [KeystrokeRecord((False, 2), 3010.0, 3100.0, 90.0)], records

# Shift held while typing: Windows stops repeating Shift once h is pressed,
# so Shift is last seen at 531. At 2560 it has been unseen for 2029 ms and is
# dropped, together with its waiting Shift -> h pair. Its release at 2700 is
# ignored. The h -> i record is unaffected.
#   h -> i: h (5.25, 1) to i (7, 0) is 2.02 key widths: near; both on the
#           right half. hold 680 - 600 = 80, dd 2560 - 600 = 1960,
#           ud 2560 - 680 = 1880.
collector = KeystrokeCollector()
records = feed(
    collector,
    [
        ("down", SHIFT, 0),
        ("down", SHIFT, 500),
        ("down", SHIFT, 531),
        ("down", H, 600),
        ("up", H, 680),
        ("down", I, 2560),
        ("up", I, 2640),
        ("up", SHIFT, 2700),
    ],
)
assert records == [KeystrokeRecord((True, 2), 80.0, 1960.0, 1880.0)], records
assert collector.held == {} and collector.pending == {}

# reset(): t and h overlap, so a pair is waiting on t. After reset() all
# state is gone: the releases are ignored and the next press starts fresh.
collector = KeystrokeCollector()
records = feed(collector, [("down", T, 0), ("down", H, 50)])
assert T in collector.pending
collector.reset()
assert collector.held == {} and collector.pending == {}
assert collector.prev_key is None
records += feed(
    collector,
    [
        ("up", T, 100),
        ("up", H, 120),
        ("down", E, 200),
        ("up", E, 270),
    ],
)
assert records == [], records
assert collector.held == {} and collector.pending == {}

print("All collector checks passed.")
