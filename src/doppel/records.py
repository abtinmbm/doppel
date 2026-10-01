"""Data records produced by the keystroke collector.

A KeystrokeRecord describes one pair of consecutive key presses (k1 then k2).
It contains only timings and a coarse label for the pair (see
keymap.relation). It never contains the keys themselves.

Definitions:
    hold = k1 up   - k1 down
    dd   = k2 down - k1 down   (down-to-down)
    ud   = k2 down - k1 up     (up-to-down, negative when the keys overlap)
All timings are in milliseconds. For every record, ud = dd - hold.

Labels come in two shapes:
    (same_half, bucket), e.g. (False, 2)   both keys are letters: keyboard
                                           geometry of the pair
    (kind1, kind2), e.g. ("space", "left") at least one key is not a letter:
                                           the kind of each key
"""

from dataclasses import dataclass

# A pair's label: geometry for two letters, key kinds otherwise.
Label = tuple[bool, int] | tuple[str, str]


@dataclass(frozen=True)
class KeystrokeRecord:
    """Timings and label for one pair of consecutive key presses.

    Records are read-only once created, so a measurement cannot be changed
    after the fact.

    Attributes:
        label:   from keymap.relation(): (same_half, bucket) for two letters,
                 (kind1, kind2) otherwise. See the module docstring.
        hold_ms: how long k1 was held down.
        dd_ms:   time from k1 going down to k2 going down.
        ud_ms:   time from k1 coming up to k2 going down.
    """

    label: Label
    hold_ms: float
    dd_ms: float
    ud_ms: float
