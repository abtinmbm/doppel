import time

from pynput import keyboard

# Keys that are down RIGHT NOW.
# Each entry is: key -> the time (in nanoseconds) it went down.
# Key identities live here only until the key is released.
held = {}

# Keys that were still down when the NEXT key was pressed.
# Each entry is: key -> the time the next key went down.
# It is used to finish the UD calculation once that key is released.
pending = {}

# Shared notebook:
#   last_down: when the most recent real key press happened
#   last_up:   when the most recent key's release happened
#              (None = "not known yet", e.g. that key is still down)
#   prev_key:  the most recent real press (memory only, never printed or saved)
state = {"last_down": None, "last_up": None, "prev_key": None}


def on_press(key):
    # pynput calls this every time a key goes DOWN.
    # Read the stopwatch first so the timestamp is as accurate as possible.
    now = time.perf_counter_ns()

    # If this key is already in held, Windows is auto-repeating it
    # (you're holding it). It's not a new press, so ignore it.
    # This check must come BEFORE we touch any state,
    # or fake repeats would corrupt the flight times.
    if key in held:
        return

    # DD (down-to-down): previous press's down -> this press's down.
    # The very first press has no previous one, so last_down is None.
    if state["last_down"] is not None:
        dd = (now - state["last_down"]) / 1_000_000  # ns -> ms
        print("DD:", round(dd, 1), "ms")
    state["last_down"] = now  # save for the NEXT press

    # UD (up-to-down): previous key's release -> this press's down.
    prev = state["prev_key"]
    if prev is not None:
        if prev in held:
            # Overlap: the previous key hasn't come up yet, so we can't
            # finish UD now. Leave a note; on_release completes it.
            pending[prev] = now
        elif state["last_up"] is not None:
            # No overlap: the previous key was already released.
            ud = (now - state["last_up"]) / 1_000_000
            print("UD:", round(ud, 1), "ms")

    # This key is now "the previous key" for the next press.
    # Clear last_up so a stale release can't be reused: this key's
    # own release hasn't happened yet.
    state["prev_key"] = key
    state["last_up"] = None

    # Save the down-time LAST. If we saved it earlier, a double letter
    # (like "ll") would look like "the previous key is still held".
    held[key] = now


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

    # Was the next key already waiting on THIS key's release (overlap)?
    next_down = pending.pop(key, None)
    if next_down is not None:
        # UD = next key's down MINUS this key's up.
        # Negative here, because the next key went down first.
        ud = (next_down - now) / 1_000_000
        print("UD:", round(ud, 1), "ms")

    # Only the most recent press's release feeds the no-overlap case.
    # Otherwise an older key's release would overwrite the right one.
    if key == state["prev_key"]:
        state["last_up"] = now

    # `key` is only used to check for Esc. We don't print or store it.
    if key == keyboard.Key.esc:
        return False  # returning False stops the listener


# Start listening on a background thread and hook up our two functions.
with keyboard.Listener(on_press=on_press, on_release=on_release) as listener:
    listener.join()  # keep the script alive until Esc is pressed
