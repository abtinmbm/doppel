import time

from pynput import keyboard

# A shared "notebook" that both functions can read and write.
# "last" holds the time of the previous key event (None = no event yet).
state = {"last": None}


def on_press(key):
    # pynput calls this every time a key goes DOWN.
    # Read the stopwatch immediately, before doing anything else,
    # so the timestamp is as accurate as possible.
    now = time.perf_counter_ns()  # current time in nanoseconds

    if state["last"] is None:
        gap = 0  # first event ever, so there's nothing to compare against
    else:
        # Nanoseconds since the previous event, converted to milliseconds
        gap = (now - state["last"]) / 1000000

    print("down:", round(gap, 1))  # note: we never print which key it was
    state["last"] = now  # write this time in the notebook for the next event


def on_release(key):
    # pynput calls this every time a key goes UP.
    # Same three steps as on_press, just labelled "up".
    now = time.perf_counter_ns()

    if state["last"] is None:
        gap = 0
    else:
        gap = (now - state["last"]) / 1000000
    print("up:", round(gap, 1))
    state["last"] = now

    # `key` is used here only to check for Esc. We don't print or store it.
    if key == keyboard.Key.esc:
        return False  # returning False stops the listener


# Start the listener on a background thread and hook up our two functions.
with keyboard.Listener(on_press=on_press, on_release=on_release) as listener:
    listener.join()  # pause here so the script stays alive until Esc is pressed
