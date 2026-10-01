"""Checks for doppel.keymap.relation().

Each assert compares relation() on a pair of keys against the value worked
out by hand. Keys are Windows virtual key codes, as keymap.key_id() gives
them. If any check fails, Python stops and shows which line failed.
"""

from doppel.keymap import relation


def k(ch):
    """Return the virtual key code of a letter key (its uppercase ASCII code)."""
    return ord(ch.upper())


SHIFT = 0xA0  # left Shift
DIGIT_1 = 0x31  # the "1" key

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

# t (4, 0) to a (0.25, 1) is 3.88 key widths: far; both on the left half.
assert relation(k("t"), k("a")) == (True, 3)

# A key with no letter (Shift, digits) has no position, so there is no label.
assert relation(k("a"), SHIFT) is None
assert relation(DIGIT_1, k("a")) is None

print("All relation checks passed.")
