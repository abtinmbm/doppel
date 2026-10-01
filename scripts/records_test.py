"""Checks for doppel.records.KeystrokeRecord.

Builds a record from the fast "th" example, checks its fields and the
ud = dd - hold relationship, and confirms the record is read-only.
"""

from dataclasses import FrozenInstanceError

from doppel.records import KeystrokeRecord

# The fast "th" example: t held 78 ms, h went down 35 ms after t.
record = KeystrokeRecord(label=(True, 1), hold_ms=78.0, dd_ms=35.0, ud_ms=-43.0)
print(record)

# Fields are read by name.
assert record.dd_ms == 35.0
assert record.label == (True, 1)

# The timings are consistent: ud = dd - hold.
assert record.ud_ms == record.dd_ms - record.hold_ms

# Two records with the same values compare as equal.
assert record == KeystrokeRecord((True, 1), 78.0, 35.0, -43.0)

# A frozen record cannot be changed after it is created.
try:
    record.dd_ms = 999.0  # pyright: ignore[reportAttributeAccessIssue]    raise AssertionError("record should be read-only")
except FrozenInstanceError:
    pass

print("All record checks passed.")
