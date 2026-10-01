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
SPACE = 0x20
BACKSPACE = 0x08
ENTER = 0x0D

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

# If either key is not a letter, the label is the kind of each key. Letters
# become their half of the keyboard: a is on the left, h and o on the right.
assert relation(k("a"), SHIFT) == ("left", "shift")
assert relation(SHIFT, k("h")) == ("shift", "right")
assert relation(k("o"), SPACE) == ("right", "space")
assert relation(SPACE, k("t")) == ("space", "left")
assert relation(BACKSPACE, ENTER) == ("backspace", "enter")

# Keys without their own kind (digits, punctuation, Ctrl...) are "other".
assert relation(DIGIT_1, k("a")) == ("other", "left")
assert relation(SPACE, SPACE) == ("space", "space")

print("All relation checks passed.")
