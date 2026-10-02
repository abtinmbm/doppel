"""Checks for doppel.trust.TrustEngine with scripted sequences of trust values.

Threshold 0.1, grace 3, quiet period 60 s. "low" = 0.05 (below threshold),
"good" = 0.5. Times are in seconds.
"""

from doppel.trust import TrustEngine

LOW, GOOD = 0.05, 0.5


def feed(engine, values):
    """Feed (name, trust, t) values; return the lock decision for each."""
    return [engine.update(name, trust, t) for name, trust, t in values]


# Grace: two lows, then a good value resets the count; three lows in a row
# lock on the third.
engine = TrustEngine(threshold=0.1, grace=3, quiet_s=60)
assert feed(engine, [("typing", GOOD, 0), ("typing", LOW, 10), ("typing", LOW, 20),
                     ("typing", GOOD, 30), ("typing", LOW, 40), ("typing", LOW, 50),
                     ("typing", LOW, 59)]) == [False, False, False, False, False, False, True]

# Evidence expiry: after 100 s of silence (> 60), the FIRST low value locks.
engine = TrustEngine(threshold=0.1, grace=3, quiet_s=60)
assert feed(engine, [("typing", LOW, 0), ("typing", LOW, 100)]) == [False, True]

# After a quiet period a good value restores normal grace: one low no longer locks.
engine = TrustEngine(threshold=0.1, grace=3, quiet_s=60)
assert feed(engine, [("typing", GOOD, 0), ("typing", GOOD, 100), ("typing", LOW, 110)]) == [False, False, False]

# reset() clears everything: a low right after does not lock (normal grace).
engine.reset()
assert engine.fused() is None
assert feed(engine, [("typing", LOW, 200)]) == [False]

# Fusion: equal weights average the fresh values: (0.2 + 0.6) / 2 = 0.4.
engine = TrustEngine(threshold=0.1, grace=3, quiet_s=60)
feed(engine, [("typing", 0.2, 0), ("mouse", 0.6, 0)])
assert abs(engine.fused() - 0.4) < 1e-12

# Weights 3 : 1 -> (3 * 0.2 + 1 * 0.6) / 4 = 0.3.
engine = TrustEngine(threshold=0.1, grace=3, quiet_s=60, weights={"typing": 3, "mouse": 1})
feed(engine, [("typing", 0.2, 0), ("mouse", 0.6, 0)])
assert abs(engine.fused() - 0.3) < 1e-12

# A stale scorer is left out, not counted as 0: mouse 0.9 at t=0, typing
# 0.05 at t=50 -> (0.9 + 0.05) / 2 = 0.475; typing 0.05 at t=100 -> mouse is
# now 100 s old (> 60) and dropped -> fused = 0.05.
engine = TrustEngine(threshold=0.1, grace=3, quiet_s=60)
feed(engine, [("mouse", 0.9, 0), ("typing", 0.05, 50)])
assert abs(engine.fused() - 0.475) < 1e-12
feed(engine, [("typing", 0.05, 100)])
assert abs(engine.fused() - 0.05) < 1e-12

# current(t): the fused value while fresh, None once 60 s have passed.
assert abs(engine.current(150) - 0.05) < 1e-12
assert engine.current(161) is None

print("All trust checks passed.")
