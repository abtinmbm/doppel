"""The live Doppel app: score the owner's typing and lock when it stops matching.

Ties every part together: the keyboard listener produces records, the
storage writer keeps saving them (so the owner's data keeps growing), the
typing scorer turns them into trust values, and the trust engine decides
when to lock. By default it runs as a dry run: it prints "WOULD LOCK"
instead of locking, so untuned settings can never lock the owner out.

How it works:
    1. Startup: load the database key, decrypt the owner's stored records
       from one or more databases, and build a typing scorer from them
       (70% train the profile, 30% calibrate it; see scorer.py).
    2. The keyboard callbacks only put (record, arrival time) on a queue,
       so they stay fast: scoring and locking never run inside the hook.
    3. A worker thread takes records off the queue and runs them through a
       LivePipeline:
         a. A gap longer than the quiet period since the previous record
            empties the scorer's window, so the first window after a break
            holds only new typing.
         b. The record goes to the storage writer.
         c. The scorer returns a trust value every `stride` records once its
            window is full; the trust engine fuses it and decides.
         d. On a lock decision: lock the screen (or print WOULD LOCK in a
            dry run), then reset the engine and the scorer's window; in lock
            mode the collector is also reset (on the hook's thread), since
            releases are not seen while the screen is locked.
    4. Ctrl+C in the terminal stops the app. The worker finishes the queued
       records and the writer saves the last batch.

Usage:
    uv run python -m doppel.app                       dry run, profile from data/doppel.db
    uv run python -m doppel.app --profile A.db B.db   build the profile from these databases
    uv run python -m doppel.app --quiet               do not print trust values
    uv run python -m doppel.app --lock                really lock (only after tuning)
"""

import argparse
import ctypes
import queue
import threading
import time
from collections.abc import Callable
from pathlib import Path

from doppel.keystore import get_or_create_key
from doppel.listener import run
from doppel.records import KeystrokeRecord
from doppel.scorer import TypingScorer, build_typing_scorer
from doppel.storage import DB_PATH, RecordStore
from doppel.trust import TrustEngine
from doppel.writer import StorageWriter


def lock_workstation() -> None:
    """Lock the screen with Windows' own lock (the secure lock screen).

    Raises:
        OSError: if Windows refuses (LockWorkStation returns 0).
    """
    if not ctypes.windll.user32.LockWorkStation():
        raise OSError("LockWorkStation failed")


def load_records(key: bytes, paths: list[Path]) -> list[KeystrokeRecord]:
    """Decrypt and concatenate the records of several databases, in order.

    List older databases first, so the time-ordered train/calibration split
    in build_typing_scorer stays in time order.
    """
    records: list[KeystrokeRecord] = []
    for path in paths:
        store = RecordStore(key, path)
        records += store.load_all()
        store.close()
    return records


class LivePipeline:
    """Runs each record through storage, the scorer and the trust engine."""

    def __init__(
        self,
        scorer: TypingScorer,
        engine: TrustEngine,
        store: Callable[[KeystrokeRecord], None],
        lock: Callable[[], None],
        report: Callable[[float, float | None, int, bool], None] | None = None,
    ):
        """Connect the parts.

        Args:
            scorer: the owner's typing scorer.
            engine: the trust engine that decides when to lock.
            store: called with every record (the storage writer's submit).
            lock: called on a lock decision (locks, or prints in a dry run).
            report: called with (trust, fused trust, low streak, locked) for
                every trust value, e.g. to print it.
        """
        self.scorer = scorer
        self.engine = engine
        self.store = store
        self.lock = lock
        self.report = report
        self.last_t: float | None = None

    def process(self, record: KeystrokeRecord, t: float) -> bool:
        """Handle one record that arrived at time t (seconds); True if it caused a lock."""
        # After a quiet period, start a fresh window of new typing only.
        if self.last_t is not None and t - self.last_t > self.engine.quiet_s:
            self.scorer.reset()
        self.last_t = t

        self.store(record)
        trust = self.scorer.observe(record)
        if trust is None:
            return False

        locked = self.engine.update(self.scorer.name, trust, t)
        if self.report is not None:
            self.report(trust, self.engine.fused(), self.engine.low_streak, locked)
        if locked:
            self.lock()
            self.engine.reset()
            self.scorer.reset()
        return locked


def run_app(
    profile_paths: list[Path],
    store_path: Path = DB_PATH,
    lock_screen: bool = False,
    echo: bool = True,
) -> None:
    """Run the live app until Ctrl+C.

    Args:
        profile_paths: databases holding the owner's typing, oldest first.
        store_path: where new records are stored.
        lock_screen: really lock; False = dry run (print WOULD LOCK).
        echo: print every trust value.
    """
    key = get_or_create_key()
    records = load_records(key, profile_paths)
    scorer = build_typing_scorer(records)
    engine = TrustEngine()
    print(
        f"Profile from {len(records)} records ({len(scorer.calibration)} calibration windows). "
        f"Window {scorer.window}, threshold {engine.threshold}, grace {engine.grace}, "
        f"quiet {engine.quiet_s:.0f} s. {'LOCK MODE' if lock_screen else 'Dry run'}; Ctrl+C stops."
    )

    writer = StorageWriter(key, store_path)
    reset_event = threading.Event()  # asks the hook thread to reset its collector

    def do_lock() -> None:
        if lock_screen:
            reset_event.set()
            lock_workstation()
        else:
            print("WOULD LOCK")

    def report(trust: float, fused: float | None, streak: int, locked: bool) -> None:
        if echo:
            print(f"trust {trust:.3f}  fused {fused:.3f}  low streak {streak}")

    pipeline = LivePipeline(scorer, engine, writer.submit, do_lock, report)
    inbox: queue.Queue[tuple[KeystrokeRecord, float] | None] = queue.Queue()
    errors: list[BaseException] = []

    def worker() -> None:
        try:
            while (item := inbox.get()) is not None:
                pipeline.process(*item)
        except BaseException as e:  # noqa: BLE001 - reported after shutdown
            errors.append(e)

    thread = threading.Thread(target=worker, name="doppel-app")
    thread.start()
    try:
        run(
            on_record=lambda r: inbox.put((r, time.monotonic())),
            stop_on_esc=False,
            reset_event=reset_event,
        )
    except KeyboardInterrupt:
        pass  # Ctrl+C is the normal way to stop
    finally:
        inbox.put(None)
        thread.join()
        writer.stop()
    if errors:
        raise errors[0]


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Doppel live app (dry run unless --lock). Ctrl+C stops it.")
    parser.add_argument("--profile", nargs="+", type=Path, default=[DB_PATH], metavar="DB",
                        help=f"databases with the owner's typing, oldest first (default: {DB_PATH})")
    parser.add_argument("--store", type=Path, default=DB_PATH, metavar="DB",
                        help=f"where new records are stored (default: {DB_PATH})")
    parser.add_argument("--lock", action="store_true", help="really lock the screen (only after tuning)")
    parser.add_argument("--quiet", action="store_true", help="do not print trust values")
    args = parser.parse_args()
    run_app(args.profile, args.store, lock_screen=args.lock, echo=not args.quiet)
