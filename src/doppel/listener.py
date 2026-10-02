"""Live keyboard listener that feeds a KeystrokeCollector.

Installs a pynput keyboard hook, timestamps every key event with a monotonic
nanosecond clock, and passes it to the collector. Each record the collector
produces is handed to a callback.

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
    6. The main thread waits for the hook in half-second steps rather than
       one long join(): on Windows a plain join() can keep Ctrl+C from
       reaching Python, and Ctrl+C is how a collection run is stopped.

Stopping:
    Print-only mode stops when Esc is released (development only; in the
    live app that would be an off switch for anyone at the keyboard).
    Storing mode ignores Esc, which is pressed constantly in normal work,
    and stops with Ctrl+C in its terminal window. Either way the writer is
    stopped in a finally block, so the last batch is saved.

Usage:
    uv run python -m doppel.listener                          print records; Esc stops
    uv run python -m doppel.listener --store                  store in data/doppel.db; Ctrl+C stops
    uv run python -m doppel.listener --store PATH             store in PATH instead
    uv run python -m doppel.listener --store --quiet          store without printing records
"""

import argparse
import threading
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


def run(
    on_record: Callable[[KeystrokeRecord], None] = print_record,
    stop_on_esc: bool = True,
    reset_event: threading.Event | None = None,
) -> None:
    """Listen to the keyboard until Esc is released or Ctrl+C is pressed.

    Args:
        on_record: function called with each KeystrokeRecord produced.
        stop_on_esc: stop when Esc is released (development use).
        reset_event: when another thread sets it (e.g. after locking the
            screen), the collector is reset at the next key event. The reset
            happens on the hook's own thread, which owns the collector.

    Raises:
        KeyboardInterrupt: when Ctrl+C is pressed in the terminal. The hook is
            removed before it propagates.
    """
    collector = KeystrokeCollector()

    def reset_if_asked() -> None:
        """Reset the collector if another thread asked for it."""
        if reset_event is not None and reset_event.is_set():
            collector.reset()
            reset_event.clear()

    def on_press(key: keyboard.Key | keyboard.KeyCode | None) -> None:
        now = time.perf_counter_ns()
        reset_if_asked()
        vk = key_id(key)
        if vk is None:
            return
        record = collector.key_down(vk, now)
        if record is not None:
            on_record(record)

    def on_release(key: keyboard.Key | keyboard.KeyCode | None) -> bool | None:
        now = time.perf_counter_ns()
        reset_if_asked()
        vk = key_id(key)
        if vk is not None:
            record = collector.key_up(vk, now)
            if record is not None:
                on_record(record)

        # Development only: releasing Esc stops the listener.
        if stop_on_esc and key == keyboard.Key.esc:
            return False
        return None

    # Leaving the with block (normally, or because of Ctrl+C) removes the hook.
    with keyboard.Listener(on_press=on_press, on_release=on_release) as listener:
        while listener.is_alive():
            listener.join(0.5)  # short waits let Ctrl+C through on Windows


def run_and_store(path: Path = DB_PATH, echo: bool = True) -> int:
    """Listen until Ctrl+C is pressed, storing every record encrypted.

    Esc is ignored, since it is pressed constantly in normal work. The key is
    loaded here, before listening starts, so a key problem shows up
    immediately. The writer is stopped in a finally block, so the last,
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
        run(on_record=on_record, stop_on_esc=False)
    except KeyboardInterrupt:
        pass  # Ctrl+C is the normal way to stop a storing run
    finally:
        writer.stop()
    return count


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Live keyboard listener. Print-only: Esc stops it. --store: Ctrl+C stops it."
    )
    parser.add_argument(
        "--store",
        nargs="?",
        const=str(DB_PATH),
        metavar="PATH",
        help=f"also store records, encrypted (default path: {DB_PATH})",
    )
    parser.add_argument(
        "--quiet", action="store_true", help="with --store: do not print each record"
    )
    args = parser.parse_args()
    if args.store:
        print(f"Storing records in {args.store}. Press Ctrl+C in this window to stop.")
        stored = run_and_store(Path(args.store), echo=not args.quiet)
        print(f"Stored {stored} records in {args.store}.")
    else:
        run()
