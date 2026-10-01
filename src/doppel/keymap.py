"""Keyboard identity, geometry and key kinds for Doppel.

Identifies each key by its Windows virtual key code, and converts a pair of
consecutive keys into a coarse label: where the keys sit on a QWERTY keyboard
when both are letters, or what kind of key each one is otherwise. Key codes
and letters are used only in memory while the label is computed; the label is
the only value meant to leave this module.

How it works:
    1. key_id() reads the virtual key code (vk) from a pynput key. The vk
       names the physical key and does not change with Shift, Ctrl or Caps
       Lock, so a key's press and release always get the same id. (pynput's
       own key objects compare by character, so "A" on press and "a" on
       release would look like two different keys.)
    2. vk_letter() converts a vk to its letter. Windows gives the letter keys
       A-Z the codes 0x41-0x5A, which are the same numbers as the ASCII
       codes for "A"-"Z", so chr() recovers the letter.
    3. Each letter gets an (x, y) position on the keyboard, measured in key
       widths. y is the row (0 = top). x is the column plus a per-row offset,
       because each lower row is shifted right on a real keyboard.
    4. The distance between two keys is the straight-line distance between
       their positions: sqrt((x2 - x1)^2 + (y2 - y1)^2).
    5. The distance is converted to one of four buckets, so the stored value
       is coarse and shared by many different letter pairs.
    6. Each key is also tagged left or right of the keyboard's centre. Two keys
       are on the "same half" when their tags match.
    7. The label for a pair of letters is (same_half, bucket).
    8. If either key is not a letter, the label is instead the kind of each
       key: "left" or "right" for a letter (its half of the keyboard),
       "space", "shift", "backspace", "enter", or "other" for everything else
       (digits, punctuation, Ctrl, arrows...). Example: "o" then Space gives
       ("right", "space"). This keeps pairs around Space and Shift, which are
       very frequent and personal, in separate groups without recording which
       letters were typed.

Limitation:
    The vk follows the keyboard layout's letter, not the physical position.
    On a QWERTY layout the two are the same; on another layout the positions
    in KEY_POS would be wrong.
"""

import math

from doppel.records import Label

# Letters on each row, from top to bottom.
ROWS = ["qwertyuiop", "asdfghjkl", "zxcvbnm"]

# Horizontal offset of each row, in key widths, relative to the top row.
STAGGER = [0.0, 0.25, 0.75]

# Letters on the left side of the keyboard. All other letters are on the right.
LEFT_HALF = set("qwertasdfgzxcvb")

# Windows virtual key codes of the letter keys A and Z. The codes in between
# are the other letters, in alphabetical order.
VK_A = 0x41
VK_Z = 0x5A

# Kinds of the non-letter keys that get their own kind. The codes are the
# same in Windows and in browsers (JavaScript key codes), except that the
# Windows keyboard hook reports left and right Shift separately.
SPECIAL_KINDS = {
    0x20: "space",
    0x10: "shift",  # Shift (browsers, and Windows' generic code)
    0xA0: "shift",  # left Shift (Windows)
    0xA1: "shift",  # right Shift (Windows)
    0x08: "backspace",
    0x0D: "enter",
}

# Build the lookup table: letter -> (x, y).
# For each letter, x is its index within its row plus that row's offset,
# and y is the index of its row. enumerate() supplies the indexes.
KEY_POS: dict[str, tuple[float, int]] = {}
for row_index, letters in enumerate(ROWS):
    for col_index, ch in enumerate(letters):
        x = col_index + STAGGER[row_index]
        y = row_index
        KEY_POS[ch] = (x, y)


def key_id(key: object) -> int | None:
    """Return the virtual key code of a pynput key, or None if it has none.

    Letter and symbol keys arrive as KeyCode objects, which carry .vk.
    Special keys (Shift, Space, Enter) arrive as members of the Key enum,
    whose .value is a KeyCode carrying .vk. Left and right Shift have
    different codes, so they stay separate keys.
    """
    vk = getattr(key, "vk", None)
    if vk is None:
        # Key enum members keep their KeyCode in .value.
        value = getattr(key, "value", None)
        vk = getattr(value, "vk", None)
    return vk


def vk_letter(vk: int) -> str | None:
    """Return the lowercase letter for a virtual key code, or None.

    Only the letter keys A-Z have a letter. Every other key (digits,
    punctuation, Shift, Space) returns None.
    """
    if VK_A <= vk <= VK_Z:
        return chr(vk).lower()
    return None


def distance_bucket(distance: float) -> int:
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


def key_kind(vk: int) -> str:
    """Return the kind of a key: "left"/"right" for a letter, else its kind.

    Letters are tagged with their half of the keyboard. Space, Shift,
    Backspace and Enter have their own kinds; every other key is "other".
    """
    letter = vk_letter(vk)
    if letter is not None:
        return "left" if letter in LEFT_HALF else "right"
    return SPECIAL_KINDS.get(vk, "other")


def relation(prev_vk: int, vk: int) -> Label:
    """Return the label for two consecutive keys.

    Args:
        prev_vk: virtual key code of the first key.
        vk: virtual key code of the second key.

    Returns:
        For two letters, (same_half, bucket):
            same_half: True if both keys are on the same side of the keyboard.
            bucket:    distance bucket between the two keys (see
                       distance_bucket).
        Otherwise (kind of first key, kind of second key), see key_kind.
    """
    prev_char = vk_letter(prev_vk)
    char = vk_letter(vk)
    if prev_char is None or char is None:
        return (key_kind(prev_vk), key_kind(vk))

    # Look up each key's (x, y) position and unpack it into two variables.
    x1, y1 = KEY_POS[prev_char]
    x2, y2 = KEY_POS[char]

    # Straight-line distance between the two positions, in key widths.
    distance = math.hypot(x2 - x1, y2 - y1)

    # Two keys are on the same half when both are in LEFT_HALF or both are not,
    # which is the same as their left/right tags being equal.
    same_half = (prev_char in LEFT_HALF) == (char in LEFT_HALF)

    return (same_half, distance_bucket(distance))
