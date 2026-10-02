"""Prints hold time, DD and UD for every key press.

For each physical key press, prints the hold time and the two flight times
that link it to the previous key, in milliseconds. Key names are never
printed. Press Esc to stop.

Definitions (k1 is the previous key, k2 is the current key):
    hold = k2 up   - k2 down
    DD   = k2 down - k1 down   (down-to-down)
    UD   = k2 down - k1 up     (up-to-down)
UD is negative when k2 goes down before k1 is released, which happens when
typing fast. For every pair, UD = DD - hold(k1).

How it works:
    1. `held` maps each key that is down right now to its press time.
       A down event for a key already in `held` is an auto-repeat and is
       ignored, so each physical press is counted once.
    2. DD is computed when a key goes down, from the stored press time of the
       previous key.
    3. UD needs the previous key's release time. If that key was already
       released, UD is computed immediately from `last_up`.
    4. If the previous key is still down (overlap), the current press time is
       stored in `pending` under the previous key. When that key is released,
       UD is computed as the stored press time minus the release time.
    5. `last_up` is updated only for the most recent press, so an older key's
       release cannot be attached to the wrong pair.
    6. Key identities exist in memory only while the key is down, except for
       the most recent key, which is kept until the next press.

Limitation (early experiment, kept for reference):
    Keys are matched by pynput key objects, which compare by character. A
    key pressed while Shift is down ("A") and released after Shift ("a") does
    not match, so it stays in `held` (later presses are ignored as
    auto-repeats) and any UD waiting in `pending` is never printed.
    doppel.collector avoids this by matching on virtual key codes
    (doppel.keymap.key_id).
"""

import time
from typing import Any

from pynput import keyboard

# Keys that are down right now.
# Each entry is: key -> the time (in nanoseconds) it went down.
held = {}

# Keys that were still down when the next key was pressed.
# Each entry is: key -> the time the next key went down.
# The entry is used to compute UD when that key is released, then removed.
pending = {}

# Shared between both callbacks. All values are timestamps except prev_key.
#   last_down: time of the most recent real key press
#   last_up:   time the most recent key was released (None while it is down)
#   prev_key:  the most recent real key press
state: dict[str, Any] = {"last_down": None, "last_up": None, "prev_key": None}


def on_press(key):
    """Compute DD, and UD where possible, for a key that has just gone down."""
    now = time.perf_counter_ns()

    # Auto-repeat events are ignored before any state is touched, so they
    # cannot change last_down, last_up or prev_key.
    if key in held:
        return

    # DD: this press minus the previous press. The first press has no
    # previous press, so there is nothing to print.
    if state["last_down"] is not None:
        dd = (now - state["last_down"]) / 1_000_000
        print("DD:", round(dd, 1), "ms")
    state["last_down"] = now

    # UD: this press minus the previous key's release.
    prev = state["prev_key"]
    if prev is not None:
        if prev in held:
            # The previous key is still down, so its release time is not known
            # yet. Store this press time; on_release completes the UD.
            pending[prev] = now
        elif state["last_up"] is not None:
            # The previous key was already released.
            ud = (now - state["last_up"]) / 1_000_000
            print("UD:", round(ud, 1), "ms")

    # This key becomes the previous key for the next press. Its release has
    # not happened yet, so last_up is cleared.
    state["prev_key"] = key
    state["last_up"] = None

    # held is updated last so that the check above looks only at earlier
    # keys. A repeated letter such as "ll" is then treated as a new press.
    held[key] = now


def on_release(key):
    """Print the hold time, and any UD waiting on this key, for a key that has come up.

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

    # If the next key was pressed while this key was still down, finish that
    # UD now. The next key went down first, so the result is negative.
    next_down = pending.pop(key, None)
    if next_down is not None:
        ud = (next_down - now) / 1_000_000
        print("UD:", round(ud, 1), "ms")

    # Only the most recent press feeds the no-overlap case in on_press.
    if key == state["prev_key"]:
        state["last_up"] = now

    # The key is only compared against Esc. It is never printed or stored.
    if key == keyboard.Key.esc:
        return False


# Run the listener on a background thread. join() keeps the script alive
# until a callback returns False.
with keyboard.Listener(on_press=on_press, on_release=on_release) as listener:
    listener.join()
