"""Summarises an encrypted Doppel database without showing any record.

Decrypts every batch with the DPAPI-protected key and prints only
aggregates: rows, days, record count, how many records have each kind of
label, and median timings. Run from the project folder:

    uv run python scripts/db_summary.py [PATH]      (default: data/doppel.db)
"""

import statistics
import sys
from collections import Counter
from pathlib import Path

from doppel.keystore import get_or_create_key
from doppel.storage import DB_PATH, RecordStore

path = Path(sys.argv[1]) if len(sys.argv) > 1 else DB_PATH
if not path.exists():
    sys.exit(f"No database at {path}.")

store = RecordStore(get_or_create_key(), path)
rows = store.conn.execute("SELECT day, COUNT(*) FROM batches GROUP BY day ORDER BY day").fetchall()
records = store.load_all()
store.close()

print(f"{path}: {sum(n for _, n in rows)} encrypted batches, {len(records)} records")
for day, n in rows:
    print(f"  {day}: {n} batches")
if records:
    # Geometry labels start with True/False; key-kind labels with a string.
    shapes = Counter("geometry" if isinstance(r.label[0], bool) else "key kinds" for r in records)
    print(f"  labels: {shapes['geometry']} geometry, {shapes['key kinds']} key kinds")
    print(
        f"  median hold {statistics.median(r.hold_ms for r in records):.1f} ms, "
        f"DD {statistics.median(r.dd_ms for r in records):.1f} ms, "
        f"UD {statistics.median(r.ud_ms for r in records):.1f} ms"
    )
