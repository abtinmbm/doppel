"""Measures how long one 200-record flush takes.

Times RecordStore.flush() on a temporary database, and separately the
in-Python part of it (shuffle + JSON + AES-GCM encryption), which holds
Python's global interpreter lock and could delay the keyboard hook thread
even when it runs on the writer thread. The rest is mostly the SQLite commit,
disk work that releases the lock. Prints the median and the maximum over
RUNS flushes. Run from the project folder.
"""

import json
import os
import statistics
import time
from pathlib import Path

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from doppel.records import KeystrokeRecord
from doppel.storage import BATCH_SIZE, NONCE_BYTES, RecordStore, _record_to_row, _shuffle_rng

RUNS = 50

path = Path("data") / "flush_timing.db"
path.unlink(missing_ok=True)
key = AESGCM.generate_key(bit_length=256)

# A realistic batch: both label shapes, typical timing values.
batch = [
    KeystrokeRecord((False, 2), 95.3 + i % 40, 180.7 + i % 90, 85.4) if i % 3
    else KeystrokeRecord(("right", "space"), 88.1, 140.2 + i % 60, 52.1)
    for i in range(BATCH_SIZE)
]

store = RecordStore(key, path, batch_size=BATCH_SIZE + 1)  # never flushes on its own
flush_ms = []
for _ in range(RUNS):
    store.buffer = list(batch)
    start = time.perf_counter_ns()
    store.flush()
    flush_ms.append((time.perf_counter_ns() - start) / 1_000_000)
store.close()

# The in-Python part alone: the same steps flush() does before the commit.
aes = AESGCM(key)
cpu_ms = []
for _ in range(RUNS):
    records = list(batch)
    start = time.perf_counter_ns()
    _shuffle_rng.shuffle(records)
    plaintext = json.dumps([_record_to_row(r) for r in records]).encode("utf-8")
    aes.encrypt(os.urandom(NONCE_BYTES), plaintext, b"2026-10-01")
    cpu_ms.append((time.perf_counter_ns() - start) / 1_000_000)

path.unlink()
print(f"Whole flush ({BATCH_SIZE} records, {RUNS} runs): median {statistics.median(flush_ms):.2f} ms, max {max(flush_ms):.2f} ms")
print(f"Shuffle + JSON + encrypt only:             median {statistics.median(cpu_ms):.3f} ms, max {max(cpu_ms):.3f} ms")
