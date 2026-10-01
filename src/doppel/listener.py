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
    5. run_and_store() passes every record to a StorageWriter, which
       encrypts and writes it on a background thread, so the keyboard
       callbacks only ever put a record on a queue.

Usage:
    uv run python -m doppel.listener                  print records only
    uv run python -m doppel.listener --store          also store them in data/doppel.db
    uv run python -m doppel.listener --store PATH     store them in PATH instead

Development only:
    Releasing Esc stops the listener. This must be removed before the live
    app, where it would be an off switch for anyone at the keyboard.
"""

import argparse
import time
from collections.abc import Callable
from pathlib import Path

from pynput import keyboard

from doppel.collector import KeystrokeCollector
from doppel.keymap import key_id
from doppel.keystore import get_or_create_key
from doppel.records import KeystrokeRecord
from doppel.storage import DB_PATH
from doppel.writer import StorageWriter


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


def run_and_store(path: Path = DB_PATH, echo: bool = True) -> int:
    """Listen until Esc is released, storing every record encrypted.

    The key is loaded here, before listening starts, so a key problem shows
    up immediately. The writer is stopped in a finally block, so the last,
    partial batch is saved even if the listener stops with an error.

    Args:
        path: database file.
        echo: also print each record.

    Returns:
        The number of records stored.
    """
    writer = StorageWriter(get_or_create_key(), path)
    count = 0

    def on_record(record: KeystrokeRecord) -> None:
        nonlocal count  # count lives in run_and_store, not in this function
        count += 1
        if echo:
            print_record(record)
        writer.submit(record)

    try:
        run(on_record=on_record)
    finally:
        writer.stop()
    return count


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Live keyboard listener (Esc stops it).")
    parser.add_argument(
        "--store",
        nargs="?",
        const=str(DB_PATH),
        metavar="PATH",
        help=f"also store records, encrypted (default path: {DB_PATH})",
    )
    args = parser.parse_args()
    if args.store:
        stored = run_and_store(Path(args.store))
        print(f"Stored {stored} records in {args.store}.")
    else:
        run()
