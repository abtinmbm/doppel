"""Data records produced by the keystroke collector.

A KeystrokeRecord describes one pair of consecutive key presses (k1 then k2).
It contains only timings and a coarse keyboard-geometry label. It never
contains the keys themselves.

Definitions:
    hold = k1 up   - k1 down
    dd   = k2 down - k1 down   (down-to-down)
    ud   = k2 down - k1 up     (up-to-down, negative when the keys overlap)
All timings are in milliseconds. For every record, ud = dd - hold.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class KeystrokeRecord:
    """Timings and label for one pair of consecutive key presses.

    Records are read-only once created, so a measurement cannot be changed
    after the fact.

    Attributes:
        label:   (same_half, bucket) from keymap.relation(), or None when
                 either key is not a letter (space, Shift, Enter...).
        hold_ms: how long k1 was held down.
        dd_ms:   time from k1 going down to k2 going down.
        ud_ms:   time from k1 coming up to k2 going down.
    """

    label: tuple[bool, int] | None
    hold_ms: float
    dd_ms: float
    ud_ms: float
