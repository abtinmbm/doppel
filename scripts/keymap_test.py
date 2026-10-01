"""Checks the lookup tables and key identity in doppel.keymap.

Confirms the position of two letters, that every letter appears exactly once
in the table, which half of the keyboard two letters belong to, that key_id()
gives one id per physical key whatever modifiers are held, that vk_letter()
maps only the letter keys to letters, and that key_kind() gives each key its
kind.
"""

from pynput.keyboard import Key, KeyCode

from doppel.keymap import KEY_POS, LEFT_HALF, ROWS, key_id, key_kind, vk_letter

# "t" is column 4 of the top row, which has no offset.
assert KEY_POS["t"] == (4.0, 0), KEY_POS["t"]

# "a" is the first key of the second row, shifted right by that row's
# offset of 0.25.
assert KEY_POS["a"] == (0.25, 1), KEY_POS["a"]

# Every letter appears exactly once: 26 entries, and the rows contain no
# repeated letters (otherwise a later row would overwrite an earlier one).
assert len(KEY_POS) == 26, len(KEY_POS)
assert len("".join(ROWS)) == 26

# "g" is on the left half of the keyboard, "h" is on the right.
assert "g" in LEFT_HALF
assert "h" not in LEFT_HALF

# The T key as the Windows listener reports it: with Shift ("T"), without
# ("t") and with Ctrl (control character 0x14). pynput compares these by
# character, so it treats them as different keys; key_id() gives all three
# the same code, 0x54.
shift_t = KeyCode.from_vk(0x54, char="T")
plain_t = KeyCode.from_vk(0x54, char="t")
ctrl_t = KeyCode.from_vk(0x54, char="\x14")
assert shift_t != plain_t  # the mismatch that key_id() avoids
assert key_id(shift_t) == key_id(plain_t) == key_id(ctrl_t) == 0x54

# Special keys keep their code in .value. Left and right Shift differ.
assert key_id(Key.shift) == 0xA0
assert key_id(Key.shift_r) == 0xA1

# No code available: nothing to identify the key by.
assert key_id(None) is None
assert key_id(KeyCode.from_char("t")) is None

# Letters are 0x41 ("A") to 0x5A ("Z"); the codes just outside are not.
assert vk_letter(0x41) == "a"
assert vk_letter(0x54) == "t"
assert vk_letter(0x5A) == "z"
assert vk_letter(0x40) is None
assert vk_letter(0x5B) is None
assert vk_letter(0x31) is None  # the "1" key
assert vk_letter(0xA0) is None  # left Shift

# Key kinds: letters by half of the keyboard; Shift in all three codes (the
# generic 0x10 used by browsers, and Windows' left 0xA0 and right 0xA1);
# Space, Backspace and Enter; everything else (here "1" and Ctrl) is "other".
assert key_kind(0x41) == "left"  # a
assert key_kind(0x47) == "left"  # g
assert key_kind(0x48) == "right"  # h
assert key_kind(0x10) == key_kind(0xA0) == key_kind(0xA1) == "shift"
assert key_kind(0x20) == "space"
assert key_kind(0x08) == "backspace"
assert key_kind(0x0D) == "enter"
assert key_kind(0x31) == "other"  # the "1" key
assert key_kind(0x11) == "other"  # Ctrl

print("All keymap checks passed.")
