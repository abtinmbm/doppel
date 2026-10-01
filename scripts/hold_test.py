"""Prints the hold time of every key press.

For each physical key press, prints how long the key stayed down, in
milliseconds. Key names are never printed. Press Esc to stop.

How it works:
    1. When a key goes down, its press time is stored in `held`, labelled by
       the key.
    2. While a key is held, Windows sends repeated key-down events with no
       key-up between them. A down event for a key already in `held` is one
       of these repeats and is ignored, so each physical press is counted once.
    3. When a key goes up, its entry is removed from `held`. The hold time is
       the release time minus the stored press time. Matching by key keeps the
       result correct when keys overlap (down, down, up, up).
    4. Key identities exist in memory only while the key is down.

Limitation (early experiment, kept for reference):
    Keys are matched by pynput key objects, which compare by character. A
    key pressed while Shift is down ("A") and released after Shift ("a") does
    not match, so it stays in `held` and its later presses are ignored as
    auto-repeats. doppel.collector avoids this by matching on virtual key
    codes (doppel.keymap.key_id).
"""

import time

from pynput import keyboard

# Keys that are down right now.
# Each entry is: key -> the time (in nanoseconds) it went down.
held = {}


def on_press(key):
    """Record the press time of a key that has just gone down."""
    now = time.perf_counter_ns()

    # A key already in held is being auto-repeated, not pressed again.
    if key in held:
        return

    held[key] = now


def on_release(key):
    """Print the hold time of the key that has just come up.

    Returns False when Esc is released, which stops the listener.
    """
    now = time.perf_counter_ns()

    # Remove the key and get back its press time. This is None if the key was
    # already down before the script started, in which case there is nothing
    # to measure.
    down_time = held.pop(key, None)

    if down_time is not None:
        # Press-to-release time, converted from nanoseconds to milliseconds.
        hold = (now - down_time) / 1_000_000
        print("hold:", round(hold, 1), "ms")

    # The key is only compared against Esc. It is never printed or stored.
    if key == keyboard.Key.esc:
        return False


# Run the listener on a background thread. join() keeps the script alive
# until a callback returns False.
with keyboard.Listener(on_press=on_press, on_release=on_release) as listener:
    listener.join()
