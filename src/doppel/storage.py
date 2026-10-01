"""Encrypted storage for keystroke records.

Records are kept in memory until a full batch is ready, then the batch is
shuffled, encrypted and written to SQLite as a single row.

How it works:
    1. add() appends a record to an in-memory buffer. When the buffer holds
       batch_size records, flush() is called.
    2. flush():
       a. Shuffles the buffer using the operating system's cryptographic
          random number generator, so the typing order is not kept.
       b. Converts each record to a list [label1, label2, hold, dd, ud],
          where (label1, label2) is the record's label: (same_half, bucket)
          such as [false, 2, ...], or two key kinds such as
          ["space", "left", ...]. The whole batch becomes JSON bytes.
       c. Encrypts the JSON with AES-GCM using a fresh random 12-byte nonce.
          The day is passed as associated data: it is stored unencrypted, but
          decryption fails if it is changed.
       d. Inserts one row (day, nonce, data) and empties the buffer.
    3. load_all() reads every row, decrypts it with its own nonce and day,
       and converts the JSON back into KeystrokeRecords.

Stored unencrypted: the row id, the day and the nonce. Batch contents are
encrypted and authenticated, so changing the data, nonce or day makes
decryption fail with InvalidTag.
"""

import json
import os
import secrets
import sqlite3
from datetime import date
from pathlib import Path

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from doppel.records import KeystrokeRecord

# Location of the database, inside the git-ignored data folder.
DB_PATH = Path("data") / "doppel.db"

# Number of records encrypted together in one row.
BATCH_SIZE = 200

# AES-GCM nonce length in bytes. A new random nonce is used for every batch.
NONCE_BYTES = 12

# Random number generator backed by the operating system, used for shuffling.
_shuffle_rng = secrets.SystemRandom()


def _record_to_row(record: KeystrokeRecord) -> list:
    """Convert a record to a flat list that JSON can store.

    Both label shapes are pairs, so the label becomes the first two values.
    JSON keeps true/false, numbers and strings apart, so the label comes back
    with the same types.
    """
    label1, label2 = record.label
    return [label1, label2, record.hold_ms, record.dd_ms, record.ud_ms]


def _row_to_record(row: list) -> KeystrokeRecord:
    """Convert a flat list from JSON back into a record."""
    label1, label2, hold_ms, dd_ms, ud_ms = row
    return KeystrokeRecord((label1, label2), hold_ms, dd_ms, ud_ms)


class RecordStore:
    """Buffers records and writes them to SQLite in encrypted batches."""

    def __init__(self, key: bytes, path: Path = DB_PATH, batch_size: int = BATCH_SIZE):
        """Open (or create) the database.

        Args:
            key: 32-byte AES-GCM key, from keystore.get_or_create_key().
            path: database file.
            batch_size: number of records per encrypted batch.
        """
        path.parent.mkdir(parents=True, exist_ok=True)
        self.aes = AESGCM(key)
        self.batch_size = batch_size
        self.buffer: list[KeystrokeRecord] = []

        self.conn = sqlite3.connect(path)
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS batches (
                id    INTEGER PRIMARY KEY,
                day   TEXT NOT NULL,
                nonce BLOB NOT NULL,
                data  BLOB NOT NULL
            )
            """
        )
        self.conn.commit()

    def add(self, record: KeystrokeRecord) -> None:
        """Add a record, writing a batch once the buffer is full."""
        self.buffer.append(record)
        if len(self.buffer) >= self.batch_size:
            self.flush()

    def flush(self) -> None:
        """Shuffle, encrypt and write the buffered records as one row."""
        if not self.buffer:
            return

        _shuffle_rng.shuffle(self.buffer)
        rows = [_record_to_row(r) for r in self.buffer]
        plaintext = json.dumps(rows).encode("utf-8")

        # The day is stored in the clear and bound to the ciphertext as
        # associated data.
        day = date.today().isoformat()  # noqa: DTZ011
        nonce = os.urandom(NONCE_BYTES)
        data = self.aes.encrypt(nonce, plaintext, day.encode("utf-8"))

        self.conn.execute(
            "INSERT INTO batches (day, nonce, data) VALUES (?, ?, ?)",
            (day, nonce, data),
        )
        self.conn.commit()
        self.buffer = []

    def load_all(self) -> list[KeystrokeRecord]:
        """Decrypt every stored batch and return all records.

        Raises:
            cryptography.exceptions.InvalidTag: if the key is wrong or any
                row has been modified.
        """
        records = []
        rows = self.conn.execute("SELECT day, nonce, data FROM batches ORDER BY id")
        for day, nonce, data in rows:
            plaintext = self.aes.decrypt(nonce, data, day.encode("utf-8"))
            for row in json.loads(plaintext):
                records.append(_row_to_record(row))
        return records

    def close(self) -> None:
        """Write any remaining records and close the database."""
        self.flush()
        self.conn.close()
