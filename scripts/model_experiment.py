"""Compares window-scoring variants on Aalto to find the strongest typing model.

Every variant scores the same windows of the same owners and impostors, so
their EERs can be compared owner by owner (paired), as in aalto_experiment.py.

Data: a fixed random sample of Aalto participants (QWERTY, physical
keyboard). The first N_OWNERS are owners (and each other's impostors); the
next N_BACKGROUND are a separate background population, used only for the
population statistics of the likelihood-ratio variants. Background people are
never owners or impostors, so those variants cannot learn the impostors.

Every record uses Doppel's stored label (geometry + key kinds) and the
groups of scorer.label_groups (label -> "nonletter" -> "all").

Variants (higher score = more anomalous):
    base      current scorer: features hold, DD, UD; z = (x - median) / MAD
              per group; score = sum over groups and features of |sum of z|
    f2        base with hold and DD only (UD = DD - hold adds nothing new)
    log2      f2 on log(hold) and log(DD + 1): proportional differences
    chi2      f2 with squared sums: sum over groups of (sum z)^2 / n_group
    sqrtw     f2 with sum over groups of |sum z| / sqrt(n_group)
    llr       likelihood ratio, hold and DD: for each record,
                  sum_f [ |x - m_pop| / b_pop + ln b_pop ] - [ |x - m_own| / b_own + ln b_own ]
              (Laplace log-likelihoods, b = MAD / ln 2); the window score is
              minus its mean: high when the owner fits worse than the population
    llr_log   llr on log(hold) and log(DD + 1)
    f2_clip   f2 with each z capped at +-3 (one long pause cannot dominate)
    log2_clip log2 with each z capped at +-3 (also _c2, _c5: caps of 2 and 5)
    llr_log_clip  llr_log with each feature's per-record log-likelihood
              ratio capped at +-3

Development and confirmation: variants are compared and tuned on the default
sample (seed 0). A different seed (second argument) draws a fresh sample and
excludes everyone in the seed-0 sample, so the final choice can be confirmed
on people never used for any decision.

Reported: mean EER at N = 50 and 100 records (windows every 5 records), and
the paired difference from base at N = 100 with a 95% interval.
Run from the project folder: uv run python scripts/model_experiment.py [owners] [seed]
"""

import math
import sys
import time
import zipfile
from collections.abc import Hashable

import numpy as np

from doppel.aalto import ZIP_PATH, load_sample
from doppel.metrics import eer
from doppel.scorer import label_groups

N_OWNERS = int(sys.argv[1]) if len(sys.argv) > 1 else 500
N_BACKGROUND = 500
N_IMPOSTORS = 50
WINDOW_SIZES = [50, 100]
STRIDE = 5
MIN_COUNT = 5
MIN_MAD = {"raw": 1.0, "log": 0.01}  # 1 ms on the raw scale; ~1% on the log scale
SEED = int(sys.argv[2]) if len(sys.argv) > 2 else 0
LN2 = math.log(2)


def raw3(records):
    """hold, DD, UD in ms."""
    return np.array([[r.hold_ms, r.dd_ms, r.ud_ms] for r in records], dtype=float)


def raw2(records):
    """hold, DD in ms."""
    return np.array([[r.hold_ms, r.dd_ms] for r in records], dtype=float)


def log2(records):
    """log(hold), log(DD + 1); DD can be 0 when two keys go down together."""
    x = raw2(records)
    return np.log(np.maximum(x, 0.0) + 1.0)


class Profile:
    """Per-group median and MAD of a feature matrix, with label_groups fallback."""

    def __init__(self, records, values, min_mad):
        rows: dict[Hashable, list[int]] = {}
        for i, r in enumerate(records):
            for key in label_groups(r):
                rows.setdefault(key, []).append(i)
        self.median, self.mad = {}, {}
        for key, idx in rows.items():
            if len(idx) >= MIN_COUNT:
                g = values[idx]
                med = np.median(g, axis=0)
                self.median[key] = med
                self.mad[key] = np.maximum(np.median(np.abs(g - med), axis=0), min_mad)

    def lookup(self, records):
        """Median rows, MAD rows and the group used, for each record."""
        med, mad, used = [], [], []
        for r in records:
            key = next(k for k in label_groups(r) if k in self.median)
            med.append(self.median[key])
            mad.append(self.mad[key])
            used.append(key)
        return np.array(med), np.array(mad), used


def window_sum_scores(z, groups, size, mode):
    """Window scores from per-record z rows, aggregated per group."""
    index: dict[Hashable, int] = {}
    ids = np.array([index.setdefault(g, len(index)) for g in groups])
    out = []
    for s in range(0, len(z) - size + 1, STRIDE):
        sums = np.zeros((len(index), z.shape[1]))
        counts = np.zeros(len(index))
        np.add.at(sums, ids[s : s + size], z[s : s + size])
        np.add.at(counts, ids[s : s + size], 1)
        present = counts > 0
        if mode == "abs":
            v = np.abs(sums[present]).sum()
        elif mode == "chi2":
            v = (sums[present] ** 2 / counts[present, None]).sum()
        else:  # sqrtw
            v = (np.abs(sums[present]) / np.sqrt(counts[present, None])).sum()
        out.append(v / size)
    return np.array(out)


def window_mean_scores(per_record, size):
    """Window scores as the mean of a per-record score."""
    c = np.concatenate([[0.0], np.cumsum(per_record)])
    starts = np.arange(0, len(per_record) - size + 1, STRIDE)
    return (c[starts + size] - c[starts]) / size


def laplace_cost(x, med, mad):
    """Negative Laplace log-likelihood per record, summed over features."""
    b = mad / LN2
    return (np.abs(x - med) / b + np.log(b)).sum(axis=1)


start = time.perf_counter()
z_file = zipfile.ZipFile(ZIP_PATH)
excluded: set = set()
if SEED != 0:
    # Confirmation run: leave out everyone in the development sample.
    dev, _ = load_sample(z_file, np.random.default_rng(0), N_OWNERS + N_BACKGROUND, min_test_records=max(WINDOW_SIZES))
    excluded = set(dev)
rng = np.random.default_rng(SEED)
data, _ = load_sample(z_file, rng, N_OWNERS + N_BACKGROUND + len(excluded), min_test_records=max(WINDOW_SIZES))
data = {p: d for p, d in data.items() if p not in excluded}
pids = list(data)[: N_OWNERS + N_BACKGROUND]
print(f"seed {SEED}; {len(excluded)} development-sample people excluded")
owners, background = pids[:N_OWNERS], pids[N_OWNERS:]
print(f"{len(owners)} owners, {len(background)} background people; loaded in {time.perf_counter() - start:.0f} s")

# Population statistics from the background people's training typing.
bg_records = [r for p in background for r in data[p][0]]
population = {
    "raw": Profile(bg_records, raw2(bg_records), MIN_MAD["raw"]),
    "log": Profile(bg_records, log2(bg_records), MIN_MAD["log"]),
}

VARIANTS = ["base", "f2", "log2", "chi2", "sqrtw", "llr", "llr_log", "f2_clip", "log2_clip", "log2_clip_c2", "log2_clip_c5", "llr_log_clip"]
CLIP = 3.0
eers = {v: {n: [] for n in WINDOW_SIZES} for v in VARIANTS}


def stream_scores(train, profiles, records, n):
    """Window scores of one stream of records for every variant."""
    out = {}
    p3, p2, pl = profiles
    med, mad, used = p3.lookup(records)
    z3 = (raw3(records) - med) / mad
    out["base"] = window_sum_scores(z3, used, n, "abs")

    x2 = raw2(records)
    med, mad, used = p2.lookup(records)
    z2 = (x2 - med) / mad
    out["f2"] = window_sum_scores(z2, used, n, "abs")
    out["chi2"] = window_sum_scores(z2, used, n, "chi2")
    out["sqrtw"] = window_sum_scores(z2, used, n, "sqrtw")
    out["f2_clip"] = window_sum_scores(np.clip(z2, -CLIP, CLIP), used, n, "abs")
    pm, pmad, _ = population["raw"].lookup(records)
    own_cost = laplace_cost(x2, med, mad)
    pop_cost = laplace_cost(x2, pm, pmad)
    out["llr"] = window_mean_scores(own_cost - pop_cost, n)  # high = fits owner worse

    xl = log2(records)
    med, mad, used = pl.lookup(records)
    zl = (xl - med) / mad
    out["log2"] = window_sum_scores(zl, used, n, "abs")
    out["log2_clip"] = window_sum_scores(np.clip(zl, -CLIP, CLIP), used, n, "abs")
    out["log2_clip_c2"] = window_sum_scores(np.clip(zl, -2.0, 2.0), used, n, "abs")
    out["log2_clip_c5"] = window_sum_scores(np.clip(zl, -5.0, 5.0), used, n, "abs")
    pm, pmad, _ = population["log"].lookup(records)
    out["llr_log"] = window_mean_scores(laplace_cost(xl, med, mad) - laplace_cost(xl, pm, pmad), n)
    # Per feature: own cost minus population cost, capped, then summed.
    b_own, b_pop = mad / LN2, pmad / LN2
    per_feature = (np.abs(xl - med) / b_own + np.log(b_own)) - (np.abs(xl - pm) / b_pop + np.log(b_pop))
    out["llr_log_clip"] = window_mean_scores(np.clip(per_feature, -CLIP, CLIP).sum(axis=1), n)
    return out


for owner in owners:
    train, test = data[owner]
    profiles = (
        Profile(train, raw3(train), MIN_MAD["raw"]),
        Profile(train, raw2(train), MIN_MAD["raw"]),
        Profile(train, log2(train), MIN_MAD["log"]),
    )
    others = [p for p in owners if p != owner]
    k = min(N_IMPOSTORS, len(others))  # small test runs have fewer owners
    impostors = [others[i] for i in rng.choice(len(others), size=k, replace=False)]
    for n in WINDOW_SIZES:
        genuine = stream_scores(train, profiles, test, n)
        imp = [stream_scores(train, profiles, data[p][1], n) for p in impostors]
        for v in VARIANTS:
            eers[v][n].append(eer(genuine[v], np.concatenate([s[v] for s in imp])))

print(f"\nMean EER over {len(owners)} owners ({N_IMPOSTORS} impostors each)")
print(f"{'variant':<10}" + "".join(f"{'N=' + str(n):>10}" for n in WINDOW_SIZES))
for v in VARIANTS:
    print(f"{v:<10}" + "".join(f"{np.mean(eers[v][n]):>10.3f}" for n in WINDOW_SIZES))

n = max(WINDOW_SIZES)
base = np.array(eers["base"][n])
print(f"\nPaired EER difference vs base at N={n} (negative = better), 95% interval")
for v in VARIANTS[1:]:
    diff = np.array(eers[v][n]) - base
    half = 1.96 * diff.std(ddof=1) / np.sqrt(len(diff))
    print(f"{v:<10}{diff.mean():+.3f}  [{diff.mean() - half:+.3f}, {diff.mean() + half:+.3f}]")
print(f"\nTotal time {time.perf_counter() - start:.0f} s.")
