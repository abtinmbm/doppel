"""The trust engine: fuses scorer outputs and decides when to lock.

Each scorer (typing now; mouse later) reports trust values from 0 (not the
owner) to 1 (the owner) as its evidence comes in. The engine combines the
latest values and decides whether the screen should lock.

How it works:
    1. Fusion. The engine keeps each scorer's latest trust value and when it
       arrived. The fused trust is the weighted mean of the values that are
       still fresh (at most quiet_s seconds older than the newest one). A
       scorer with nothing fresh is simply left out, never counted as 0, and
       the others are reweighted.
    2. Grace. A single low window is weak evidence: the owner is sometimes
       tired or distracted. The engine locks only after `grace` fused values
       in a row fall below `threshold`. Any value at or above it resets the
       count.
    3. Evidence expiry. If no scorer has reported anything for more than
       quiet_s seconds (the owner walked away, or someone is only reading),
       all earlier evidence expires. Until a good value is seen again, the
       FIRST low value locks, with no grace: someone who sits down after a
       quiet period must look like the owner straight away. Once a value at
       or above the threshold is seen, normal grace returns.
    4. reset() starts fresh, e.g. after the screen was locked and the owner
       logged back in through Windows (which re-authenticates them).

Why expiry instead of a slowly falling number: with a single lock threshold
the only thing a falling trust value changes is how much new evidence is
needed to lock. Expiry states that rule directly: after a quiet period, one
bad window is enough.
"""

# Defaults; the threshold and grace are tuned by the lock simulation.
THRESHOLD = 0.05
GRACE = 3
QUIET_S = 60.0


class TrustEngine:
    """Fuses trust values from scorers and decides when to lock."""

    def __init__(
        self,
        threshold: float = THRESHOLD,
        grace: int = GRACE,
        quiet_s: float = QUIET_S,
        weights: dict[str, float] | None = None,
    ):
        """Set the lock rule.

        Args:
            threshold: fused trust below this counts as a low value.
            grace: low values in a row needed to lock in normal use.
            quiet_s: seconds without evidence after which evidence expires.
            weights: weight per scorer name (default 1 for every scorer).
        """
        self.threshold = threshold
        self.grace = grace
        self.quiet_s = quiet_s
        self.weights = weights or {}
        self.reset()

    def reset(self) -> None:
        """Forget all evidence and start in normal (grace) mode."""
        self.latest: dict[str, tuple[float, float]] = {}  # name -> (trust, time)
        self.last_t: float | None = None
        self.low_streak = 0
        self.after_quiet = False

    def fused(self) -> float | None:
        """Weighted mean of the fresh trust values, or None if there are none."""
        if self.last_t is None:
            return None
        total = weight_sum = 0.0
        for name, (trust, t) in self.latest.items():
            if self.last_t - t <= self.quiet_s:  # stale scorers are left out
                w = self.weights.get(name, 1.0)
                total += w * trust
                weight_sum += w
        return total / weight_sum if weight_sum else None

    def update(self, name: str, trust: float, t: float) -> bool:
        """Record a scorer's trust value at time t (seconds); return True to lock."""
        # A long silence before this value: earlier evidence has expired.
        if self.last_t is not None and t - self.last_t > self.quiet_s:
            self.latest.clear()
            self.low_streak = 0
            self.after_quiet = True

        self.latest[name] = (trust, t)
        self.last_t = t
        fused = self.fused()
        assert fused is not None  # the value just added is fresh

        if fused < self.threshold:
            self.low_streak += 1
        else:
            self.low_streak = 0
            self.after_quiet = False  # the owner has shown up again

        needed = 1 if self.after_quiet else self.grace
        return self.low_streak >= needed

    def current(self, t: float) -> float | None:
        """Fused trust at time t, or None if all evidence has expired."""
        if self.last_t is None or t - self.last_t > self.quiet_s:
            return None
        return self.fused()
