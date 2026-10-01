"""Error rates for an authentication detector: FAR, FRR and EER.

A detector gives every typing sample an anomaly score: low means "looks like
the owner", high means "looks like someone else". A threshold turns scores
into decisions: a sample is accepted if its score is at or below the
threshold, and rejected otherwise.

Definitions:
    FAR (false accept rate) = share of impostor samples that are accepted.
    FRR (false reject rate) = share of genuine samples that are rejected.
    EER (equal error rate)  = the error rate at the threshold where FAR and
                              FRR are equal. One number that summarises a
                              detector without choosing a threshold first.

How it works:
    1. Every score that occurs (genuine or impostor) is tried as a threshold.
       Between two neighbouring scores no decision changes, so these are the
       only thresholds that matter.
    2. Raising the threshold accepts more samples: FAR can only go up and
       FRR can only go down. The two curves therefore cross once.
    3. Scores are discrete, so FAR and FRR are rarely exactly equal at any
       threshold. eer() takes the threshold where they are closest and
       returns their average there.
"""

import numpy as np
from numpy.typing import ArrayLike


def far_frr(
    genuine: ArrayLike, impostor: ArrayLike, threshold: float
) -> tuple[float, float]:
    """Return (FAR, FRR) at one threshold.

    Args:
        genuine: anomaly scores of the owner's samples.
        impostor: anomaly scores of other people's samples.
        threshold: samples with a score at or below this are accepted.
    """
    genuine = np.asarray(genuine, dtype=float)
    impostor = np.asarray(impostor, dtype=float)
    far = float(np.mean(impostor <= threshold))
    frr = float(np.mean(genuine > threshold))
    return far, frr


def eer(genuine: ArrayLike, impostor: ArrayLike) -> float:
    """Return the equal error rate of a detector's scores.

    Args:
        genuine: anomaly scores of the owner's samples.
        impostor: anomaly scores of other people's samples.

    Returns:
        The average of FAR and FRR at the threshold where they are closest,
        between 0 (perfect separation) and 1.
    """
    genuine = np.asarray(genuine, dtype=float)
    impostor = np.asarray(impostor, dtype=float)

    # Candidate thresholds: every distinct score, in increasing order.
    thresholds = np.unique(np.concatenate([genuine, impostor]))

    # FAR and FRR at every threshold at once. Comparing a column of
    # thresholds with a row of scores gives one row of True/False per
    # threshold; the mean of each row is the share of samples that pass.
    far = np.mean(impostor[None, :] <= thresholds[:, None], axis=1)
    frr = np.mean(genuine[None, :] > thresholds[:, None], axis=1)

    # The threshold where the two rates are closest.
    best = int(np.argmin(np.abs(far - frr)))
    return float((far[best] + frr[best]) / 2)
