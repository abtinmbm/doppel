"""Live keyboard listener that feeds a KeystrokeCollector.

Installs a pynput keyboard hook, timestamps every key event with a monotonic
nanosecond clock, and passes it to the collector. Each record the collector
produces is handed to a callback. Press Esc to stop.

How it works:
    1. pynput calls on_press for every key-down and on_release for every
       key-up, on its own background thread.
    2. Each callback reads time.perf_counter_ns() as its first step so the
       timestamp is as close to the real event as possible, then passes the
       key and the time to the collector.
    3. The collector returns a KeystrokeRecord or None. Records are passed
       to on_record; keys are never passed on.
"""

import time

from pynput import keyboard

from doppel.collector import KeystrokeCollector


def print_record(record):
    """Print a record's label and timings on one line."""
    print(
        f"label={record.label}  "
        f"hold={record.hold_ms:.1f}  "
        f"dd={record.dd_ms:.1f}  "
        f"ud={record.ud_ms:.1f}"
    )


def run(on_record=print_record):
    """Listen to the keyboard until Esc is released.

    Args:
        on_record: function called with each KeystrokeRecord produced.
    """
    collector = KeystrokeCollector()

    def on_press(key):
        now = time.perf_counter_ns()
        record = collector.key_down(key, now)
        if record is not None:
            on_record(record)

    def on_release(key):
        now = time.perf_counter_ns()
        record = collector.key_up(key, now)
        if record is not None:
            on_record(record)

        # Releasing Esc stops the listener.
        if key == keyboard.Key.esc:
            return False

    with keyboard.Listener(on_press=on_press, on_release=on_release) as listener:
        listener.join()


if __name__ == "__main__":
    run()
