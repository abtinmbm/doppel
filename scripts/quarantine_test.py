"""Checks for doppel.quarantine.Quarantine on a sequence worked out by hand.

Window 3. Records are numbered by their hold time so they are easy to follow.
"""

from doppel.quarantine import Quarantine
from doppel.records import KeystrokeRecord


def rec(n):
    """Record number n (hold = n ms)."""
    return KeystrokeRecord((True, 1), float(n), 100.0, 100.0 - n)


released = []
q = Quarantine(3, released.append)

for n in (1, 2, 3):
    q.add(rec(n))
assert released == []  # nothing has left the window yet
q.judge(low=False)  # records 1-3 judged once, clean
q.add(rec(4))  # record 1 leaves the window: judged, clean -> released
assert released == [rec(1)]
q.judge(low=True)  # records 2-4 flagged
q.add(rec(5))  # record 2 leaves: flagged -> dropped
q.add(rec(6))  # record 3 leaves: flagged -> dropped
q.judge(low=False)  # records 4-6 judged clean (4 stays flagged)
q.add(rec(7))  # record 4 leaves: flagged -> dropped
assert released == [rec(1)]
q.drop_all()  # a lock: records 5, 6, 7 dropped
assert released == [rec(1)] and q.kept == 1 and q.dropped == 6

# close(): judged and clean -> released; never judged -> dropped.
released = []
q = Quarantine(3, released.append)
for n in (1, 2, 3):
    q.add(rec(n))
q.judge(low=False)
q.add(rec(4))  # record 1 released now
q.close()  # 2 and 3 judged clean -> released; 4 never judged -> dropped
assert released == [rec(1), rec(2), rec(3)] and q.kept == 3 and q.dropped == 1

print("All quarantine checks passed.")
