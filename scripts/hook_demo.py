"""Prints the raw keyboard event stream as timing gaps.

For every key press and key release, prints "down" or "up" and the number of
milliseconds since the previous event of either kind. Key names are never
printed. Press Esc to stop.

How it works:
    1. pynput installs a keyboard hook that calls on_press for every key-down
       and on_release for every key-up, in any window.
    2. Each callback reads time.perf_counter_ns(), a monotonic nanosecond
       clock, as its first step so the timestamp is as accurate as possible.
    3. The gap is the current time minus the time stored for the previous
       event, converted from nanoseconds to milliseconds.
    4. The current time is then stored for the next event.
"""

import time

from pynput import keyboard

# Shared between both callbacks.
# "last" is the time of the previous key event in nanoseconds,
# or None before the first event.
state: dict[str, int | None] = {"last": None}


def on_press(key):
    """Print the gap since the previous event, labelled "down"."""
    now = time.perf_counter_ns()

    # The first event has no previous event, so its gap is 0.
    if state["last"] is None:
        gap = 0
    else:
        # Nanoseconds since the previous event, converted to milliseconds.
        gap = (now - state["last"]) / 1_000_000

    print("down:", round(gap, 1))
    state["last"] = now


def on_release(key):
    """Print the gap since the previous event, labelled "up".

    Returns False when Esc is released, which stops the listener.
    """
    now = time.perf_counter_ns()

    if state["last"] is None:
        gap = 0
    else:
        gap = (now - state["last"]) / 1_000_000

    print("up:", round(gap, 1))
    state["last"] = now

    # The key is only compared against Esc. It is never printed or stored.
    if key == keyboard.Key.esc:
        return False


# Run the listener on a background thread. join() keeps the script alive
# until a callback returns False.
with keyboard.Listener(on_press=on_press, on_release=on_release) as listener:
    listener.join()
