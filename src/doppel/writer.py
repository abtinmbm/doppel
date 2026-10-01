"""Background writer that stores records without slowing the keyboard hook.

Encrypting a batch and writing it to disk takes time. If that ran inside a
keyboard callback, the next key events would be delayed (late timestamps
corrupt the timings) and Windows may skip a hook that responds too slowly.
StorageWriter moves that work to a background thread.

How it works (producer-consumer):
    1. The keyboard callbacks are the producer. submit() only puts the record
       on a queue.Queue, which is thread-safe and takes microseconds.
    2. A background thread is the consumer. It takes records off the queue
       one at a time (waiting while the queue is empty) and passes each to a
       RecordStore, which buffers, shuffles, encrypts and writes batches.
    3. The thread creates its own RecordStore, because an SQLite connection
       may only be used by the thread that opened it.
    4. stop() puts a sentinel (None) on the queue. The queue is first in,
       first out, so every record submitted before stop() is stored first.
       When the thread reaches the sentinel it closes the store (which
       writes the last, partial batch) and ends. stop() waits for that.
    5. If storing fails in the thread (e.g. the disk is full), the error is
       kept and raised again by stop(), so a failure is never silent.

Design notes:
    - The queue has no size limit: a full queue would make submit() wait,
      which would freeze the keyboard hook. Records are small and contain no
      keys, so a backlog is harmless.
    - The thread is not a daemon thread. A daemon thread is killed when the
      program exits, which would lose the last partial batch; callers stop
      the writer explicitly instead (in a try/finally).
"""

import queue
import threading
from pathlib import Path

from doppel.records import KeystrokeRecord
from doppel.storage import BATCH_SIZE, DB_PATH, RecordStore


class StorageWriter:
    """Stores records on a background thread; submit() never blocks."""

    def __init__(
        self, key: bytes, path: Path = DB_PATH, batch_size: int = BATCH_SIZE
    ):
        """Start the background thread.

        Args:
            key: 32-byte AES-GCM key, from keystore.get_or_create_key(). It is
                loaded by the caller, so key problems show up at startup.
            path: database file.
            batch_size: number of records per encrypted batch.
        """
        # None is the sentinel that tells the thread to stop.
        self._queue: queue.Queue[KeystrokeRecord | None] = queue.Queue()
        self._error: BaseException | None = None
        self._thread = threading.Thread(
            target=self._run, args=(key, path, batch_size), name="doppel-writer"
        )
        self._thread.start()

    def submit(self, record: KeystrokeRecord) -> None:
        """Queue a record for storage. Safe to call from any thread."""
        self._queue.put(record)

    @property
    def error(self) -> BaseException | None:
        """The error that stopped the background thread, or None."""
        return self._error

    def stop(self) -> None:
        """Store everything submitted so far, then end the thread.

        Raises:
            The error from the background thread, if storing failed.
        """
        self._queue.put(None)
        self._thread.join()
        if self._error is not None:
            raise self._error

    def _run(self, key: bytes, path: Path, batch_size: int) -> None:
        """Body of the background thread: take records off the queue and store them."""
        try:
            store = RecordStore(key, path, batch_size)
        except BaseException as e:  # noqa: BLE001 - reported by stop()
            self._error = e
            return

        try:
            while True:
                record = self._queue.get()  # waits while the queue is empty
                if record is None:
                    break
                store.add(record)
        except BaseException as e:  # noqa: BLE001 - reported by stop()
            self._error = e
        finally:
            # Write the last, partial batch. If that also fails, keep the
            # first error, since it explains what went wrong.
            try:
                store.close()
            except BaseException as e:  # noqa: BLE001 - reported by stop()
                if self._error is None:
                    self._error = e
