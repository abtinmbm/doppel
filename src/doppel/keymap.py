"""Keyboard geometry for Doppel.

Converts a pair of consecutive keys into a coarse label based on where the
keys sit on a QWERTY keyboard. Letters are used only in memory while the label
is computed; the label is the only value meant to leave this module.

How it works:
    1. Each letter gets an (x, y) position on the keyboard, measured in key
       widths. y is the row (0 = top). x is the column plus a per-row offset,
       because each lower row is shifted right on a real keyboard.
    2. The distance between two keys is the straight-line distance between
       their positions: sqrt((x2 - x1)^2 + (y2 - y1)^2).
    3. The distance is converted to one of four buckets, so the stored value
       is coarse and shared by many different letter pairs.
    4. Each key is also tagged left or right of the keyboard's centre. Two keys
       are on the "same half" when their tags match.
    5. The label for a pair of keys is (same_half, bucket).
"""

import math

# Letters on each row, from top to bottom.
ROWS = ["qwertyuiop", "asdfghjkl", "zxcvbnm"]

# Horizontal offset of each row, in key widths, relative to the top row.
STAGGER = [0.0, 0.25, 0.75]

# Letters on the left side of the keyboard. All other letters are on the right.
LEFT_HALF = set("qwertasdfgzxcvb")

# Build the lookup table: letter -> (x, y).
# For each letter, x is its index within its row plus that row's offset,
# and y is the index of its row. enumerate() supplies the indexes.
KEY_POS = {}
for row_index, letters in enumerate(ROWS):
    for col_index, ch in enumerate(letters):
        x = col_index + STAGGER[row_index]
        y = row_index
        KEY_POS[ch] = (x, y)


def key_char(key):
    """Return the lowercase letter for a pynput key, or None if it is not a letter.

    Keys without a `.char` attribute (Shift, Enter, arrows) return None.
    Uppercase letters are converted to lowercase, so Shift+T maps to "t".
    """
    char = getattr(key, "char", None)
    if char is None:
        return None
    char = char.lower()

    # Characters outside KEY_POS (digits, punctuation) have no position.
    if char not in KEY_POS:
        return None
    return char


def distance_bucket(distance):
    """Convert a distance in key widths into a bucket.

    0 = same key, 1 = neighbour (up to 1.5), 2 = near (up to 3.5), 3 = far.
    """
    if distance == 0:
        return 0
    elif distance <= 1.5:
        return 1
    elif distance <= 3.5:
        return 2
    else:
        return 3


def relation(prev_key, key):
    """Return (same_half, bucket) for two consecutive keys.

    same_half: True if both keys are on the same side of the keyboard.
    bucket:    distance bucket between the two keys (see distance_bucket).
    Returns None if either key is not a letter.
    """
    prev_char = key_char(prev_key)
    char = key_char(key)
    if prev_char is None or char is None:
        return None

    # Look up each key's (x, y) position and unpack it into two variables.
    x1, y1 = KEY_POS[prev_char]
    x2, y2 = KEY_POS[char]

    # Straight-line distance between the two positions, in key widths.
    distance = math.hypot(x2 - x1, y2 - y1)

    # Two keys are on the same half when both are in LEFT_HALF or both are not,
    # which is the same as their left/right tags being equal.
    same_half = (prev_char in LEFT_HALF) == (char in LEFT_HALF)

    return (same_half, distance_bucket(distance))
