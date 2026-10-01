"""Checks for doppel.storage.RecordStore.

Writes records in small batches to a temporary database, reads them back,
and confirms that the file holds no readable timings, that a wrong key
fails, and that changing a row's day is detected.
Run from the project folder, since the database path is relative.
"""

from pathlib import Path

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from doppel.records import KeystrokeRecord
from doppel.storage import RecordStore

path = Path("data") / "test.db"
path.unlink(missing_ok=True)  # start fresh
key = AESGCM.generate_key(bit_length=256)

originals = [
    KeystrokeRecord((False, 2), 146.9, 259.4, 112.5),
    KeystrokeRecord((True, 0), 104.2, 173.9, 69.7),
    KeystrokeRecord(None, 76.5, 93.0, 16.5),
    KeystrokeRecord((False, 3), 129.0, 130.3, 1.3),
    KeystrokeRecord((True, 1), 94.2, 182.2, 88.0),
]

# With a batch size of 3, five records give one full batch on disk and two
# records still in the buffer. close() writes the remaining two.
store = RecordStore(key, path, batch_size=3)
for record in originals:
    store.add(record)
assert store.conn.execute("SELECT COUNT(*) FROM batches").fetchone()[0] == 1
store.close()

# Reading back returns the same records. Order within a batch is shuffled,
# so the comparison ignores order.
store = RecordStore(key, path)
loaded = store.load_all()
store.close()
assert len(loaded) == 5
assert set(loaded) == set(originals)

# The database file contains no readable timings.
assert b"146.9" not in path.read_bytes()

# A different key cannot decrypt the data.
store = RecordStore(AESGCM.generate_key(bit_length=256), path)
try:
    store.load_all()
    raise AssertionError("wrong key should fail")
except InvalidTag:
    pass
store.close()

# Changing a row's day is detected, because the day is associated data.
store = RecordStore(key, path)
store.conn.execute("UPDATE batches SET day = '2000-01-01' WHERE id = 1")
store.conn.commit()
try:
    store.load_all()
    raise AssertionError("changing the day should be detected")
except InvalidTag:
    pass
store.close()

path.unlink()  # clean up
print("All storage checks passed.")
