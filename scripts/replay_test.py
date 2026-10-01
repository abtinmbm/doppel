"""Checks for doppel.replay on keystroke rows worked out by hand.

Keystrokes are (press_ms, release_ms, key_code); letter key codes are the
uppercase ASCII codes (t = 84, h = 72, e = 69).
"""

from doppel.records import KeystrokeRecord
from doppel.replay import replay

T, H, E = 84, 72, 69

# No overlap: t held 80 ms, h pressed at 130.
#   t -> h: hold 80, dd 130, ud 50; t (4, 0) to h (5.25, 1) is near, and the
#   keys are on different halves -> (False, 2).
assert replay([(0, 80, T), (130, 200, H)]) == [
    KeystrokeRecord((False, 2), 80.0, 130.0, 50.0)
]

# Three keys overlapping (fast "the"), the same times as collector_test.py:
# the rows become the same event stream and give the same two records.
assert replay([(0, 122, T), (35, 114, H), (44, 191, E)]) == [
    KeystrokeRecord((False, 2), 79.0, 9.0, -70.0),  # h -> e
    KeystrokeRecord((False, 2), 122.0, 35.0, -87.0),  # t -> h
]

# A row released before it was pressed is invalid and skipped.
assert replay([(0, 80, T), (500, 400, E), (130, 200, H)]) == [
    KeystrokeRecord((False, 2), 80.0, 130.0, 50.0)
]

# Rows can arrive in any order; events are sorted by time.
assert replay([(130, 200, H), (0, 80, T)]) == [
    KeystrokeRecord((False, 2), 80.0, 130.0, 50.0)
]

# A custom label function receives the two key codes.
assert replay([(0, 80, T), (130, 200, H)], label_fn=lambda a, b: (a, b)) == [
    KeystrokeRecord((T, H), 80.0, 130.0, 50.0)  # pyright: ignore[reportArgumentType]
]

print("All replay checks passed.")
