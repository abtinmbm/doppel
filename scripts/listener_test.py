"""Checks run_and_store()'s stopping logic without hooking the real keyboard.

doppel.listener.run is replaced by a fake that delivers three records and
then raises KeyboardInterrupt, as pressing Ctrl+C does. Expected: storing
mode asks run() not to stop on Esc, Ctrl+C is not treated as an error, all
three records are saved (the writer is stopped in finally), and the count
returned is 3. A test key is used, so the real key is never touched.
Run from the project folder.
"""

from pathlib import Path

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

import doppel.listener as listener
from doppel.records import KeystrokeRecord
from doppel.storage import RecordStore

path = Path("data") / "listener_test.db"
path.unlink(missing_ok=True)
key = AESGCM.generate_key(bit_length=256)

records = [
    KeystrokeRecord((False, 2), 80.0, 130.0, 50.0),
    KeystrokeRecord(("right", "space"), 76.5, 93.0, 16.5),
    KeystrokeRecord((True, 0), 90.0, 200.0, 110.0),
]
seen_stop_on_esc = []


def fake_run(on_record, stop_on_esc=True):
    """Deliver the records, then act like Ctrl+C."""
    seen_stop_on_esc.append(stop_on_esc)
    for record in records:
        on_record(record)
    raise KeyboardInterrupt


listener.run = fake_run
listener.get_or_create_key = lambda: key

count = listener.run_and_store(path, echo=False)
assert count == 3, count
assert seen_stop_on_esc == [False]  # Esc must not stop a storing run

store = RecordStore(key, path)
assert set(store.load_all()) == set(records)  # all three saved
store.close()

path.unlink()
print("All listener checks passed.")
