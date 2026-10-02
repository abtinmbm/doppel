"""Checks doppel.app without hooking the keyboard or locking the screen.

LivePipeline is driven with a fake scorer that returns scripted trust values,
a real TrustEngine (threshold 0.1, grace 3, quiet period 60 s), and fake
store/lock functions that only count calls. load_records is checked on two
small encrypted databases. Run from the project folder.
"""

from pathlib import Path

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from doppel.app import LivePipeline, load_records
from doppel.records import KeystrokeRecord
from doppel.storage import RecordStore
from doppel.trust import TrustEngine

RECORD = KeystrokeRecord((False, 2), 80.0, 130.0, 50.0)


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
pipeline = LivePipeline(
    scorer, engine, stored.append, lambda: locks.append(1),
    lambda trust, fused, streak, locked: reports.append((trust, streak, locked)),
)

# t = 0..4: no value, one good, then three lows in a row -> lock at t = 4.
# After the lock, the engine and the scorer's window are reset.
results = [pipeline.process(RECORD, t) for t in [0, 1, 2, 3, 4]]
assert results == [False, False, False, False, True], results
assert locks == [1] and scorer.resets == 1
assert engine.fused() is None  # engine reset after the lock
assert reports == [(0.5, 0, False), (0.05, 1, False), (0.05, 2, False), (0.05, 3, True)], reports

# t = 10: good. Then 90 s of silence (> 60): the scorer's window is emptied
# and earlier evidence expires, so the first low value (t = 100) locks.
assert pipeline.process(RECORD, 10) is False
assert pipeline.process(RECORD, 100) is True
assert locks == [1, 1]
assert scorer.resets == 3  # 1 quiet-period reset + 1 more after the second lock

# Every record was stored, including those that produced no trust value.
assert len(stored) == 7

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
