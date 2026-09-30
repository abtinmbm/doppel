import time

from pynput import keyboard

# Keys that are down RIGHT NOW.
# Each entry is: key -> the time (in nanoseconds) it went down.
# Key identities live here only until the key is released.
held = {}

# Shared notebook (stores timestamps only, never keys):
#   last_down: when the most recent real key press happened
#   last_up:   when the most recent key release happened
#              (None = "not known yet", e.g. the last key is still down)
state = {"last_down": None, "last_up": None}


def on_press(key):
    # pynput calls this every time a key goes DOWN.
    # Read the stopwatch first so the timestamp is as accurate as possible.
    now = time.perf_counter_ns()

    # If this key is already in held, Windows is auto-repeating it
    # (you're holding it). It's not a new press, so ignore it.
    # This check must come BEFORE we touch last_down / last_up,
    # or fake repeats would corrupt the flight times.
    if key in held:
        return

    # Brand new press: remember when it went down (for hold time later).
    held[key] = now

    # DD (down-to-down): previous press's down -> this press's down.
    # The very first press has no previous one, so last_down is None.
    if state["last_down"] is not None:
        DD = (now - state["last_down"]) / 1_000_000  # ns -> ms
        print("DD:", round(DD, 1), "ms")
    state["last_down"] = now  # save for the NEXT press

    # UD (up-to-down): previous key's release -> this press's down.
    # Only valid if the previous key was already released.
    if state["last_up"] is not None:
        UD = (now - state["last_up"]) / 1_000_000
        print("UD:", round(UD, 1), "ms")

    # Clear last_up AFTER using it, on every real press.
    # Otherwise a stale release from an older key could be reused
    # for an overlapped press. (Overlap case = Step B.)
    state["last_up"] = None


def on_release(key):
    # pynput calls this every time a key goes UP.
    now = time.perf_counter_ns()

    # Remove this key from held and get back when it went down.
    # Gives None if we never saw it go down (e.g. it was already
    # held when the script started).
    down_time = held.pop(key, None)

    if down_time is not None:
        # Hold time: this key's down -> this key's up, in ms.
        hold = (now - down_time) / 1_000_000
        print("hold:", round(hold, 1), "ms")  # never prints which key

    # Remember when this release happened, so the next press can
    # compute UD from it.
    state["last_up"] = now

    # `key` is only used to check for Esc. We don't print or store it.
    if key == keyboard.Key.esc:
        return False  # returning False stops the listener


# Start listening on a background thread and hook up our two functions.
with keyboard.Listener(on_press=on_press, on_release=on_release) as listener:
    listener.join()  # keep the script alive until Esc is pressed
