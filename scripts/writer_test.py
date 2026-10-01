"""Checks for doppel.writer.StorageWriter.

Submits 450 records with a batch size of 200, so the store should write two
full batches while running and the last 50 records when it is stopped: three
rows of 200, 200 and 50 records. Then checks that a failure inside the
background thread is raised by stop(). Run from the project folder.
"""

import json
import sqlite3
from pathlib import Path

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from doppel.records import KeystrokeRecord
from doppel.storage import RecordStore
from doppel.writer import StorageWriter

path = Path("data") / "writer_test.db"
path.unlink(missing_ok=True)  # start fresh
key = AESGCM.generate_key(bit_length=256)

# 450 different records (hold = i makes each one unique), both label shapes.
originals = [
    KeystrokeRecord((i % 2 == 0, i % 4) if i % 3 else ("space", "left"), float(i), float(i + 50), 50.0)
    for i in range(450)
]

writer = StorageWriter(key, path, batch_size=200)
for record in originals:
    writer.submit(record)
writer.stop()
assert writer.error is None
assert not writer._thread.is_alive()

# Three rows: two full batches written while running, the last 50 on stop().
store = RecordStore(key, path)
rows = store.conn.execute("SELECT day, nonce, data FROM batches ORDER BY id").fetchall()
sizes = [
    len(json.loads(store.aes.decrypt(nonce, data, day.encode("utf-8"))))
    for day, nonce, data in rows
]
assert sizes == [200, 200, 50], sizes

# Every record came back exactly once (order is shuffled within a batch).
loaded = store.load_all()
store.close()
assert len(loaded) == 450
assert set(loaded) == set(originals)

# A failure inside the thread is raised by stop(). A folder cannot be opened
# as a database, so creating the store fails in the background thread.
folder = Path("data") / "writer_test_folder"
folder.mkdir(exist_ok=True)
broken = StorageWriter(key, folder)
broken.submit(originals[0])
try:
    broken.stop()
    raise AssertionError("stop() should raise the background thread's error")
except sqlite3.OperationalError:
    pass
assert isinstance(broken.error, sqlite3.OperationalError)

path.unlink()  # clean up
folder.rmdir()
print("All writer checks passed.")
