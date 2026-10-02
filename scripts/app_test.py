"""Checks doppel.app without hooking the keyboard or locking the screen.

LivePipeline is driven with a fake scorer that returns scripted trust values,
a real TrustEngine (threshold 0.1, grace 3, quiet period 60 s), a real
Quarantine with a window of 2 records, and a fake lock that only counts
calls. load_records is checked on two small encrypted databases. Run from
the project folder.
"""

from pathlib import Path

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from doppel.app import LivePipeline, load_records
from doppel.quarantine import Quarantine
from doppel.records import KeystrokeRecord
from doppel.storage import RecordStore
from doppel.trust import TrustEngine



def rec(n):
    """Record number n (hold = n ms), so stored records can be told apart."""
    return KeystrokeRecord((False, 2), float(n), 130.0, 130.0 - n)


class FakeScorer:
    """Returns scripted trust values (None = no value yet); counts resets."""

    name = "typing"

    def __init__(self, values):
        self.values = list(values)
        self.resets = 0

    def observe(self, record):
        return self.values.pop(0)

    def reset(self):
        self.resets += 1


stored, locks, reports = [], [], []
scorer = FakeScorer([None, 0.5, 0.05, 0.05, 0.05, 0.5, 0.05])
engine = TrustEngine(threshold=0.1, grace=3, quiet_s=60)
quarantine = Quarantine(2, stored.append)
pipeline = LivePipeline(
    scorer, engine, quarantine, lambda: locks.append(1),
    lambda trust, fused, streak, locked: reports.append((trust, streak, locked)),
)

# t = 0..4: no value, one good, then three lows in a row -> lock at t = 4.
# After the lock, the engine and the scorer's window are reset.
results = [pipeline.process(rec(t), t) for t in [0, 1, 2, 3, 4]]
assert results == [False, False, False, False, True], results
assert locks == [1] and scorer.resets == 1
assert engine.fused() is None  # engine reset after the lock
assert reports == [(0.5, 0, False), (0.05, 1, False), (0.05, 2, False), (0.05, 3, True)], reports

# t = 10: good. Then 90 s of silence (> 60): the scorer's window is emptied
# and earlier evidence expires, so the first low value (t = 100) locks.
assert pipeline.process(rec(10), 10) is False
assert pipeline.process(rec(100), 100) is True
assert locks == [1, 1]
assert scorer.resets == 3  # 1 quiet-period reset + 1 more after the second lock

# Quarantine (window 2) let through only record 0:
#   t=1 good value judges records 0-1; t=2 low flags 1-2 and record 0 leaves
#   the window clean -> stored. Records 1 and 2 leave flagged -> dropped.
#   The lock at t=4 drops 3 and 4; the lock at t=100 drops 10 and 100.
assert stored == [rec(0)], stored
assert quarantine.kept == 1 and quarantine.dropped == 6

# load_records: databases are read in the order given.
key = AESGCM.generate_key(bit_length=256)
first = [KeystrokeRecord((True, 1), float(i), 100.0 + i, 100.0) for i in range(5)]
second = [KeystrokeRecord(("space", "left"), float(i), 50.0 + i, 50.0) for i in range(3)]
paths = [Path("data") / "app_test_a.db", Path("data") / "app_test_b.db"]
for path, records in zip(paths, [first, second]):
    path.unlink(missing_ok=True)
    store = RecordStore(key, path)
    for r in records:
        store.add(r)
    store.close()
loaded = load_records(key, paths)
assert len(loaded) == 8
assert set(loaded[:5]) == set(first) and set(loaded[5:]) == set(second)
for path in paths:
    path.unlink()

print("All app checks passed.")
