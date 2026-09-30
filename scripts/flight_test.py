import time

from pynput import keyboard

# Keys that are down RIGHT NOW.
# Each entry is: key -> the time (in nanoseconds) it went down.
# Key identities live here only until the key is released.
held = {}
state = {"last_down": None}


def on_press(key):
    # pynput calls this every time a key goes DOWN.
    # Read the stopwatch first so the timestamp is as accurate as possible.
    now = time.perf_counter_ns()

    # If this key is already in held, Windows is auto-repeating it
    # (you're holding it). It's not a new press, so ignore it.
    if key in held:
        return

    # Brand new press: remember when it went down.
    held[key] = now

    if state["last_down"] is not None:
        DD = (now - state["last_down"]) / 1_000_000
        print("DD:", round(DD, 1), "ms")
    state["last_down"] = now


def on_release(key):
    # pynput calls this every time a key goes UP.
    now = time.perf_counter_ns()

    # Remove this key from held and get back when it went down.
    # Gives None if we never saw it go down (e.g. it was already
    # held when the script started).
    down_time = held.pop(key, None)

    if down_time is not None:
        # Time between down and up, converted from ns to ms.
        hold = (now - down_time) / 1_000_000
        print("hold:", round(hold, 1), "ms")  # never prints which key

    # `key` is only used to check for Esc. We don't print or store it.
    if key == keyboard.Key.esc:
        return False  # returning False stops the listener


# Start listening on a background thread and hook up our two functions.
with keyboard.Listener(on_press=on_press, on_release=on_release) as listener:
    listener.join()  # keep the script alive until Esc is pressed
