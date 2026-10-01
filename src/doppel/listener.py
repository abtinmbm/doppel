"""Live keyboard listener that feeds a KeystrokeCollector.

Installs a pynput keyboard hook, timestamps every key event with a monotonic
nanosecond clock, and passes it to the collector. Each record the collector
produces is handed to a callback. Press Esc to stop.

How it works:
    1. pynput calls on_press for every key-down and on_release for every
       key-up, on its own background thread.
    2. Each callback reads time.perf_counter_ns() as its first step so the
       timestamp is as close to the real event as possible.
    3. The pynput key is converted to its virtual key code (keymap.key_id),
       which is the same for press and release whatever modifiers are held.
       Events without a code are ignored.
    4. The code and the time go to the collector, which returns a
       KeystrokeRecord or None. Records are passed to on_record; keys are
       never passed on.

Development only:
    Releasing Esc stops the listener. This must be removed before the live
    app, where it would be an off switch for anyone at the keyboard.
"""

import time
from collections.abc import Callable

from pynput import keyboard

from doppel.collector import KeystrokeCollector
from doppel.keymap import key_id
from doppel.records import KeystrokeRecord


def print_record(record: KeystrokeRecord) -> None:
    """Print a record's label and timings on one line."""
    print(
        f"label={record.label}  "
        f"hold={record.hold_ms:.1f}  "
        f"dd={record.dd_ms:.1f}  "
        f"ud={record.ud_ms:.1f}"
    )


def run(on_record: Callable[[KeystrokeRecord], None] = print_record) -> None:
    """Listen to the keyboard until Esc is released.

    Args:
        on_record: function called with each KeystrokeRecord produced.
    """
    collector = KeystrokeCollector()

    def on_press(key: keyboard.Key | keyboard.KeyCode | None) -> None:
        now = time.perf_counter_ns()
        vk = key_id(key)
        if vk is None:
            return
        record = collector.key_down(vk, now)
        if record is not None:
            on_record(record)

    def on_release(key: keyboard.Key | keyboard.KeyCode | None) -> bool | None:
        now = time.perf_counter_ns()
        vk = key_id(key)
        if vk is not None:
            record = collector.key_up(vk, now)
            if record is not None:
                on_record(record)

        # Development only: releasing Esc stops the listener.
        if key == keyboard.Key.esc:
            return False
        return None

    with keyboard.Listener(on_press=on_press, on_release=on_release) as listener:
        listener.join()


if __name__ == "__main__":
    run()
