"""Chooses the lock threshold and grace on the owner's own collected typing.

Time-ordered split of the stored records (oldest first): the first 70% build
the typing scorer exactly as the live app does (its own 70/30 split into
profile and calibration), the last 30% are the owner's "future" typing.

    false locks   the owner's future typing replayed through a TrustEngine;
                  every lock is false. Reported per 1,000 keystrokes.
    impostors     Aalto participants' typing scored against the owner's
                  profile: after a quiet period (first low locks) and as a
                  takeover straight after the owner's typing (grace applies).

The target of at most LOCKS_PER_DAY false locks per day becomes a limit per
1,000 keystrokes via the owner's keystrokes per day (--per-day, or estimated
as stored records / collection days, which undercounts days the collector
was not running all day, so the limit comes out stricter, never looser).
Among settings within the limit, the one catching the most takeover
impostors is chosen (doppel.tuning.choose_setting).

Caveats printed with the result: stored records are shuffled within batches
of 200, which made false locks look about 5% lower than on contiguous typing
in scripts/shuffle_bias.py; Aalto impostors type in a browser on other
keyboards, so catch rates are optimistic. Prints aggregates only, never a
record. Run from the project folder:

    uv run python scripts/owner_tuning.py [--db PATH] [--per-day N] [--impostors N]
"""

import argparse
import zipfile
from pathlib import Path

import numpy as np

from doppel.aalto import ZIP_PATH, load_sample
from doppel.app import load_records
from doppel.keystore import get_or_create_key
from doppel.scorer import STRIDE, WINDOW, build_typing_scorer
from doppel.storage import DB_PATH, RecordStore
from doppel.tuning import (
    Setting,
    choose_setting,
    false_lock_limit,
    false_locks,
    first_lock,
    trust_values,
)

THRESHOLDS = [0.001, 0.002, 0.005, 0.01, 0.02, 0.05]
GRACES = [1, 2, 3, 5]
LOCKS_PER_DAY = 1.0
TEST_SHARE = 0.3
SEED = 0

parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
parser.add_argument("--db", type=Path, default=DB_PATH)
parser.add_argument("--per-day", type=float, help="owner keystrokes per day")
parser.add_argument("--impostors", type=int, default=200, help="Aalto impostors")
args = parser.parse_args()

# 1. The owner's records, oldest first, and how many collection days.
key = get_or_create_key()
records = load_records(key, [args.db])
store = RecordStore(key, args.db)
days = store.conn.execute("SELECT COUNT(DISTINCT day) FROM batches").fetchone()[0]
store.close()
per_day = args.per_day or len(records) / days
limit = false_lock_limit(per_day, LOCKS_PER_DAY)

cut = int(len(records) * (1 - TEST_SHARE))
history, future = records[:cut], records[cut:]
scorer = build_typing_scorer(history, WINDOW, STRIDE)
print(
    f"{len(records):_} owner records over {days} day(s): {cut:_} build the scorer "
    f"({len(scorer.calibration):_} calibration windows, smallest trust "
    f"{1 / (len(scorer.calibration) + 1):.4f}), {len(future):_} test false locks."
)
print(
    f"Keystrokes per day: {per_day:_.0f} ({'given' if args.per_day else 'estimated'}) -> "
    f"limit {limit:.3f} false locks per 1,000 for {LOCKS_PER_DAY:g} per day."
)

# Trust can never fall below 1 / (calibration windows + 1), so lower
# thresholds could never lock anyone; leave them out.
floor = 1 / (len(scorer.calibration) + 1)
skipped = [th for th in THRESHOLDS if th <= floor]
THRESHOLDS = [th for th in THRESHOLDS if th > floor]
if skipped:
    print(f"Thresholds {skipped} skipped: at or below the smallest possible trust.")
# One false lock in the test typing is 1000 / len(future) per 1,000; if that
# is above the limit, the test typing is too short to show the limit is met.
resolution = 1000 / len(future)
if resolution > limit:
    print(
        f"WARNING: one false lock = {resolution:.2f} per 1,000 here, above the limit: "
        f"at least {1000 / limit:_.0f} test keystrokes are needed to measure it."
    )

# 2. Owner's future typing: one-pass trust values, checked once against observe().
z_own, g_own = scorer.profile.deviations(future)
own = trust_values(scorer, z_own, g_own)
live = [v for v in (scorer.observe(r) for r in future) if v is not None]
assert np.allclose(live, [t for _, t in own]), "trust_values differs from observe()"
scorer.reset()

# 3. Impostors: Aalto participants' typing against the owner's profile.
rng = np.random.default_rng(SEED)
sample, _ = load_sample(zipfile.ZipFile(ZIP_PATH), rng, args.impostors, min_test_records=WINDOW)
impostors = [scorer.profile.deviations(train + test) for train, test in sample.values()]

settings, quiet = [], {}
for th in THRESHOLDS:
    for g in GRACES:
        n_false = false_locks(own, WINDOW, th, g)
        keys = []
        for z_imp, g_imp in impostors:
            both = trust_values(scorer, np.vstack([z_own, z_imp]), list(g_own) + list(g_imp))
            keys.append(first_lock(both, len(future), th, g, after_quiet=False))
            if g == GRACES[0]:  # after a quiet period the first low locks, any grace
                quiet.setdefault(th, []).append(
                    first_lock(trust_values(scorer, z_imp, g_imp), 0, th, g, after_quiet=True)
                )
        hits = [k for k in keys if k is not None]
        settings.append(
            Setting(
                th,
                g,
                false_per_1000=1000 * n_false / len(future),
                caught=len(hits) / len(keys),
                median_keys=float(np.median(hits)) if hits else None,
            )
        )

# 4. Report.
print(f"\n{len(impostors)} Aalto impostors. Per setting: owner false locks per 1,000 | "
      "takeover impostors locked / median keystrokes. * = within the limit")
print(f"{'threshold':>10}" + "".join(f"{'grace ' + str(g):>22}" for g in GRACES))
for th in THRESHOLDS:
    cells = []
    for s in (s for s in settings if s.threshold == th):
        med = f"{s.median_keys:.0f}" if s.median_keys is not None else "-"
        mark = "*" if s.false_per_1000 <= limit else " "
        cells.append(f"{s.false_per_1000:.2f}{mark}| {100 * s.caught:.0f}% / {med}")
    print(f"{th:>10}" + "".join(f"{c:>22}" for c in cells))

print("\nAfter a quiet period (first low locks): impostors locked at their first window")
for th in THRESHOLDS:
    first = [k for k in quiet[th] if k == WINDOW]
    print(f"{th:>10}{100 * len(first) / len(quiet[th]):>8.0f}%")

best = choose_setting(settings, limit)
if best is None:
    print("\nNo setting meets the limit: more data, a stronger scorer, or longer windows needed.")
else:
    print(
        f"\nChosen: threshold {best.threshold}, grace {best.grace}: "
        f"{best.false_per_1000:.2f} false locks per 1,000 (limit {limit:.3f}), "
        f"{100 * best.caught:.0f}% of takeover impostors locked."
    )
print(
    "Caveats: owner false locks come from stored (batch-shuffled) order, about 5% "
    "optimistic on Aalto; Aalto impostors are other people on other keyboards, so "
    "catch rates are optimistic; one owner (n = 1)."
)
