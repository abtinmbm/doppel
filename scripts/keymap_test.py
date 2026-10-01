"""Checks the lookup tables in doppel.keymap.

Prints the position of two letters, the number of letters in the table, and
which half of the keyboard two letters belong to.

Expected output:
    (4.0, 0)
    (0.25, 1)
    26
    True False
"""

from doppel.keymap import KEY_POS, LEFT_HALF

# Position of "t" (column 4 of the top row) and "a" (first key of the second
# row, shifted right by that row's offset).
print(KEY_POS["t"])
print(KEY_POS["a"])

# Every letter appears exactly once in the table.
print(len(KEY_POS))

# "g" is on the left half of the keyboard, "h" is on the right.
print("g" in LEFT_HALF, "h" in LEFT_HALF)
