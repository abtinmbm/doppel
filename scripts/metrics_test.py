"""Checks for doppel.metrics (FAR, FRR, EER).

Each case uses a few scores small enough to work out FAR and FRR by hand at
every threshold. A sample is accepted when its score is at or below the
threshold.
"""

import math

from doppel.metrics import eer, far_frr

# far_frr at one threshold. genuine [1, 2, 3, 4], impostor [3, 5, 6, 7],
# threshold 3: impostor 3 is accepted (1 of 4 -> FAR 0.25); genuine 4 is
# rejected (1 of 4 -> FRR 0.25).
assert far_frr([1, 2, 3, 4], [3, 5, 6, 7], 3) == (0.25, 0.25)

# Perfect separation: at threshold 3 every genuine score is accepted and
# every impostor rejected, so FAR = FRR = 0.
assert eer([1, 2, 3], [4, 5, 6]) == 0.0

# Identical scores: at threshold 1, half of each side passes:
# FAR 1/2, FRR 1/2 -> EER 0.5.
assert eer([1, 2], [1, 2]) == 0.5

# Completely reversed: impostors look more like the owner than the owner.
# At threshold 2 both impostors are accepted (FAR 1) and both genuine
# samples rejected (FRR 1) -> EER 1.
assert eer([5, 6], [1, 2]) == 1.0

# FAR and FRR never exactly equal. genuine [1, 2, 3, 4, 10], impostor
# [5, 6, 7, 8]:
#   threshold 4: FAR 0/4 = 0.00, FRR 1/5 = 0.20, gap 0.20
#   threshold 5: FAR 1/4 = 0.25, FRR 1/5 = 0.20, gap 0.05  <- closest
#   threshold 6: FAR 2/4 = 0.50, FRR 1/5 = 0.20, gap 0.30
# EER = (0.25 + 0.20) / 2 = 0.225.
assert math.isclose(eer([1, 2, 3, 4, 10], [5, 6, 7, 8]), 0.225)

print("All metrics checks passed.")
