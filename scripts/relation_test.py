"""Checks for doppel.keymap.relation().

Each assert compares relation() on a pair of keys against the value worked
out by hand. If any check fails, Python stops and shows which line failed.
"""

from pynput.keyboard import Key, KeyCode

from doppel.keymap import relation


def k(ch):
    """Build a pynput key object for a character, as the keyboard listener would."""
    return KeyCode.from_char(ch)


# Different halves, 4 key widths apart: far.
assert relation(k("t"), k("o")) == (False, 3)

# Same half, one row apart in nearly the same column: neighbour.
assert relation(k("t"), k("g")) == (True, 1)

# The same key twice (the double l in "hello"): same half, distance 0.
assert relation(k("l"), k("l")) == (True, 0)

# Different halves, 3.0 key widths apart: near.
assert relation(k("f"), k("j")) == (False, 2)

# Opposite ends of the top row: far.
assert relation(k("q"), k("p")) == (False, 3)

# Uppercase is converted to lowercase, so "T" behaves like "t".
assert relation(k("T"), k("a")) == (True, 3)

# A key with no letter (Shift) has no position, so there is no label.
assert relation(k("a"), Key.shift) is None

print("All relation checks passed.")
