# Doppel.exe Devlog

One entry per work session: what I built, what broke, what I learned, and what's still open.
Newest entry at the top. Only put numbers here that I actually measured.

---

## 2026-10-01: Review, key identity, validated evaluation, label experiment, stronger scorer, trust engine and dry-run app

### Built
- **Project review and new plan.** Reviewed the whole project as a hiring engineer would. Milestone 1 is now: (1) fix key identity, (2) reproduce the CMU benchmark to validate the evaluation code, (3) Aalto free-text model + label experiment before collecting my own data, (4) writer thread + collect my data, (5) live app + README, repo public.
- **Key identity fix** (`keymap.py`, `collector.py`, `listener.py`): keys are identified by their Windows virtual key code instead of pynput's key objects. Held keys that go unseen for 2 s are dropped (lost releases), and `reset()` clears all state before a lock. `keymap_test.py` now uses asserts; `collector_test.py` has 5 new cases.
- **Evaluation code** (`metrics.py`, `detectors.py`): FAR, FRR, EER, and Euclidean / Manhattan / Scaled Manhattan detectors, with hand-worked tests (`metrics_test.py`, `detectors_test.py`).
- **CMU benchmark reproduction** (`scripts/cmu_benchmark.py`): the Killourhy & Maxion (2009) protocol on their public dataset.
- **Free-text scoring** (`replay.py`, `window_scorer.py`, `scripts/aalto_experiment.py`, plus tests): dataset keystrokes are replayed through the real collector; a window of N records is scored against a per-group profile of my typing. The collector got a `label_fn` option so experiments can try other labels.
- **Key-kind labels (option A)** (`keymap.py`, `records.py`, `storage.py`): pairs with a non-letter key are now labelled by the kind of each key, e.g. `("right", "space")`, instead of one shared `None`. Stored rows are `[label1, label2, hold, dd, ud]`. The Aalto experiment now uses Doppel's own `relation()` for this scheme, and a full 1,000-participant rerun gave identical results.
- **Background storage writer** (`writer.py`, `listener.py --store`, `scripts/db_summary.py`): the keyboard callbacks only put records on a queue; a background thread with its own database connection encrypts and writes them. `stop()` saves the last partial batch and re-raises any error from the thread. `writer_test.py` checks 450 records become rows of 200, 200 and 50, and that a failure is raised. A live test stored 207 records in 2 batches (200 + 7), and the summary script decrypted all 207.
- **Collection mode** (`listener.py --store --quiet`): storing runs ignore Esc (pressed constantly in normal work) and stop with Ctrl+C in their terminal; the hook is waited on in half-second steps so Ctrl+C gets through on Windows. `listener_test.py` checks the stop logic with a fake hook. A live test stored 368 records in 2 batches (200 + 168), all decrypted, with Esc ignored and a clean Ctrl+C exit.
- **Trust score and lock decision** (`scorer.py`, `trust.py`, `aalto.py`, `scripts/lock_simulation.py`): a typing scorer turns window scores into a 0–1 trust value calibrated against held-out windows of the owner's own typing; a trust engine fuses scorers, locks after several low values in a row (grace), and lets evidence expire after a quiet minute so the first low value then locks. The Aalto loading code moved into a shared module. Hand-worked tests: `scorer_test.py`, `trust_test.py`.
- **Dry-run live app** (`app.py`, `app_test.py`): builds my profile from stored records, scores live typing on a worker thread (scoring takes a median 0.25 ms, worst 1.41 ms per trust value, kept off the keyboard hook anyway) and prints WOULD LOCK instead of locking. In a smoke test, my own typing stayed at trust 1.000 (32 of 33 values); when my roommate typed (standing consent), trust fell to 0.013 three times in a row and WOULD LOCK fired, twice. My trust sitting at 1.0 instead of around 0.5 shows the 173-record calibration set is not yet representative.
- **README, license and CI:** README draft (the brother story, how it works, privacy design, threat model, measured results, how to run), MIT license, and pytest + GitHub Actions: `uv run pytest` runs every `scripts/*_test.py` as its own test case, and a deliberately broken script was confirmed to fail the suite. The first GitHub Actions run passed on Windows; the actions were then updated to versions that run on Node 24 (the old ones were deprecated), and the suite stayed green. 17 tests pass at the end of the day.
- **Quarantine against profile contamination** (`quarantine.py`, `quarantine_test.py`, `scripts/quarantine_simulation.py`): the live app no longer stores records straight away. A record waits until it has left the scoring window and is stored only if every window that judged it looked like me; on a lock, everything waiting is dropped. So someone else's typing is neither kept nor used to train my profile. A separate keep threshold can be stricter than the lock threshold.
- **A much stronger window scorer** (`window_scorer.py`, `scripts/model_experiment.py`): timings on a log scale (log(hold + 1), log(DD + 1)), UD dropped as redundant, and every scaled deviation capped at ±3. Chosen among 12 variants on a 500-owner development sample, then confirmed once on 500 different owners: mean EER at 100 records fell from 0.164 to 0.023. The old scorer stays available so earlier results can be reproduced exactly.
- Docstrings for the package entry point, and a note in the early scripts about the Shift limitation.
- **Started collecting my real typing:** first session stored 1,544 records in 8 encrypted batches (all 1,544 decrypted by the summary script); 860 geometry and 684 key-kind labels; median hold 89.3 ms, DD 115.0 ms, UD 16.5 ms.

### Roadblock 1: Shift made keys get stuck
**Problem:** pynput compares keys by the character typed. A key pressed with Shift down shows up as "A", but if Shift is released first, the same key's release shows up as "a". The two don't match, so the key stays "held" forever: its next presses are ignored as auto-repeats and its pair is silently lost. Ctrl+letter has the same problem.

**Process:**
- Read pynput's source to confirm it: equality and hashing are based on the character, while every Windows event also carries the virtual key code (one number per physical key).
- Switched the collector to virtual key codes, and took the label's letter from the code too.
- Lost releases (screen locked mid-press, including Doppel's own lock) needed cleanup. Measured Windows auto-repeat with `hook_test.py`: holding Shift gives a first repeat after 500.1 ms, then one every 29.6–47.4 ms. So a key that is really held keeps being "seen", and a key unseen for 2 s must have lost its release.
- Checked the tests can catch the bug: removing the stale cleanup, or the "last seen" refresh, makes `collector_test.py` fail.

**Result:**
- A live 27-record run matched what I typed, pair by pair.
- A deliberate test (Shift down, A down, Shift up, A up, then b, c) produced the A→b pair `(True, 3)` with hold 724.2, DD 1260.2, UD 536.0. That is the record the old code lost.
- An earlier attempt with a pause produced no A→b pair. That is by design: the two presses were more than 2 s apart.

### Roadblock 2: A test that could never fail
**Problem:** in `records_test.py`, the `raise AssertionError(...)` for the read-only check was on the same line as a `# pyright: ignore` comment, so it was part of the comment and never ran.

**Process:** moved it to its own line, then checked it against a fake record class that is not frozen.

**Result:** the check now fails with "record should be read-only" when it should. Lesson: a check is only useful if I have seen it fail.

### Roadblock 3: The first window score rewarded consistent impostors
**Problem:** on 100 Aalto participants, EERs were high (0.207 even for real digraphs at 100 records). Each record's score was |value − median| / spread, averaged over the window. That measures how *consistent* the typing is, not whether it is *shifted*. A steady impostor whose timings sit near my median can score lower than me.

**Process:** compared three window scores on the same 100 participants: the original, signed deviations averaged over the whole window, and signed deviations summed within each group before taking absolute values.

**Result:** the per-group signed version was best (digraph, N=100: 0.207 → 0.176), and the ranking of the labelling schemes stayed the same under all three. Summing signed deviations lets random noise cancel while a consistent shift adds up.

### Roadblock 4: The lock trade-off is poor on small profiles
**Problem:** simulating the full lock decision on 498 Aalto owners showed that a setting catching about 78% of impostors (first window after a quiet period) would also falsely lock the owner about 2.4 times per 1,000 keystrokes, many times a day for a real typist.

**Process:**
- Checked the simulation itself: its fast one-pass trust values are asserted equal to what the live scorer emits.
- Found a mechanical limit: trust can never fall below 1 / (calibration windows + 1). Aalto leaves only about 143 calibration records per person, so thresholds of 0.01–0.02 were barely reachable. Calibration now uses a window at every position, which lowers that floor.
- One owner had 99 calibration records, one short of a 100-record window; the clear error added earlier pointed straight at it, and such owners are now skipped and counted.

**Result:** the mechanism works, but each Aalto person has only ~478 training records. The thresholds stay provisional until they can be tuned on weeks of my own typing, against a target number of false locks per day.

### Roadblock 5: A test command that ran a keyboard listener
**Problem:** checking the README's "run all tests" command (`scripts\*_test.py`) also started the early live demos (`hook_test.py`, `hold_test.py`, `flight_test.py`), which hook the real keyboard and wait for Esc. One started briefly before it was stopped; it recorded nothing, but anyone following the README would hit the same trap, and pytest would collect those files too.

**Process:** stopped the run, confirmed no listener process was left, and renamed the three demos to `*_demo.py` so the `*_test.py` pattern only matches safe tests. Listing what a glob matches before running it is now a rule.

**Result:** the README command runs exactly the 15 real tests, all passing.

### Roadblock 6: My own story showed a privacy hole
**Problem:** writing the README's brother story made it obvious that the live app stored every record, including my brother's typing before a lock, and that those records would later train my profile: his data kept without consent, and a way to poison my profile just by using my PC.

**Process:** added a quarantine that holds records until the scorer has judged every window containing them, then measured it on 198 Aalto owners (5 impostors each) for keep thresholds from 0.05 to 0.5.

**Result:** at the lock threshold (0.05) it kept 55.2% of owners' typing and let 25.4% of impostor typing through; at 0.5, 37.4% and 12.4%. Quarantine blocks most impostor typing but cannot stop typing the detector cannot tell apart from mine, and on thin profiles it drops a lot of the owner's own typing. Both settings are tuned on my data.

### Roadblock 7: One long pause drowned out a whole window
**Problem:** the scorer's error on Aalto was high (0.173 EER at 100 records), and I wanted to know why before trying fancier models.

**Process:**
- Wrote one experiment comparing 12 scoring variants on the same 500 owners and 50 impostors each, with paired 95% intervals: dropping the redundant UD feature, a log scale, other ways of weighting groups, a likelihood ratio against a separate background population of 500 people, and capping each deviation.
- The log scale alone cut the error to 0.046. That was suspiciously large, so I tested the explanation: DD includes thinking pauses of up to 2 s, and one 1,500 ms pause against a typical 150 ms produced a deviation of about 34, swamping the window. If that was the cause, capping deviations on the plain scale should help too, and it did (0.040).
- Combining both (log scale + cap at 3) gave 0.026; caps of 2 and 5 gave 0.027 and 0.028, so the result does not hinge on the exact cap.
- Because I had picked the winner on the same 500 people, I confirmed it once on 500 new owners and a new background population, excluding everyone used before: 0.164 → 0.023, the same ranking.
- Checked the real scorer gives identical deviations to the experiment's version on 2,389 records, and re-checked the label choice under the new scorer (geometry + kinds still best, 0.025 vs 0.046 for real letter pairs).

**Result:** about 7 times lower error from fixing how outliers are handled, not from a bigger model. In the lock simulation it raised the share of impostors locked out at their first window after a quiet period from 78% to 90% (threshold 0.05, grace 3), while false locks only moved from 2.38 to 1.99 per 1,000 keystrokes: the threshold, a calibrated p-value, sets the false-lock rate, and a stronger scorer is what allows a lower threshold. Aalto's small calibration sets cannot reach low enough thresholds to show that; my own data can.

### Results (measured)
**CMU reproduction** (mean EER over 51 subjects, ours vs published):

| Detector | Ours | Published |
|---|---|---|
| Euclidean | 0.1705 | 0.1706 |
| Manhattan | 0.1529 | 0.1529 |
| Scaled Manhattan | 0.0960 | 0.0962 |

The evaluation code is correct. Per-subject EER (Scaled Manhattan) ranged from 0.009 to 0.325.

**Aalto label experiment** (1,000 participants; train on sentences 1–10, test on 11–15; 50 impostors each). Mean EER for a window of N records:

| Scheme | N=10 | N=25 | N=50 | N=100 |
|---|---|---|---|---|
| no label | 0.340 | 0.325 | 0.316 | 0.300 |
| geometry | 0.328 | 0.296 | 0.270 | 0.241 |
| all real digraphs | 0.318 | 0.280 | 0.249 | 0.212 |
| top-30 digraphs | 0.324 | 0.288 | 0.258 | 0.224 |
| geometry + kinds | 0.294 | 0.255 | 0.220 | 0.173 |
| top-30 + kinds | 0.292 | 0.251 | 0.215 | 0.165 |

Paired difference vs geometry at N=100 (95% interval): geometry + kinds −0.068 [−0.075, −0.062]; real digraphs −0.029 [−0.036, −0.023].

**Flush timing** (200 records, 50 flushes, two runs): the whole flush took a median of 2.45 and 2.29 ms (worst 4.44 ms); the shuffle, JSON and encryption part alone took about 0.3 ms (worst 0.415 ms). So about 2 ms is the disk commit, which the writer thread keeps away from the keyboard hook.

**Lock simulation** (498 Aalto owners, 10 impostors each, windows of 100 records, a trust value every 10): at threshold 0.05 with grace 3, 2.38 false locks per 1,000 owner keystrokes, and 78% of impostors locked out at their first window after a quiet period. Grace 5 lowered false locks to 1.64 per 1,000 keystrokes.

**Scorer experiment** (mean EER at 100 records; development sample → confirmation sample): old scorer 0.173 → 0.164; log scale + cap 0.026 → 0.023. With the new scorer: quarantine at keep threshold 0.05 let 11.2% of impostor typing through (was 25.4%), at 0.2 only 1.9%; the label re-check gave geometry + kinds 0.025, real letter pairs 0.046, geometry only 0.051.

### Design decisions
- **False-lock target: at most 1 per day** of normal use. It becomes a per-1,000-keystroke limit once my data shows how much I type per day; the threshold and grace are then chosen to catch the most impostors within it.
- **Scorer = log scale + capped deviations**, chosen on a development sample and confirmed once on separate people, because picking a winner among many variants on the same data overstates it.
- **Trust = calibrated p-value:** the share of the owner's own held-out windows that scored at least as badly (+1 smoothing), so every future scorer reports on the same 0–1 scale and fusion is meaningful.
- **Evidence expiry instead of a slowly falling trust number:** after a quiet minute, old evidence expires and the first low value locks. It makes the same decisions with one simple rule, and targets the main case: I walk away and my brother sits down.
- **Writer thread (producer–consumer):** an unbounded queue (a full queue would freeze the keyboard hook), a non-daemon thread stopped in `finally` (a daemon thread would lose the last batch), the store created on the writer thread (SQLite connections are per-thread), and errors re-raised by `stop()` so a failure is never silent.
- **CMU only validates the evaluation code.** Its features belong to one fixed password, so a CMU model cannot score Doppel's free-text records. Aalto (free text) is the real benchmark.
- **Stylometry becomes an offline experiment only.** A live buffer of typed text would hold passwords and turn Doppel into a keylogger.
- **Cut:** the C++ collector, step-up authentication, the `.exe`, and separate milestone logs (milestones now go in the devlog).
- **Own EER code** instead of scikit-learn: it is the headline metric, so I need to understand and test it.
- **Datasets are replayed through the real collector**, so the experiment evaluates exactly the records Doppel stores.
- **Window scorer:** per-group medians and MADs (typing times are right-skewed); rare groups fall back to broader ones; signed deviations summed per group.
- **Stored label = "geometry + kinds" (option A).** Letter pairs keep the geometry label. Pairs with a non-letter key get the kinds of both keys (left letter, right letter, space, shift, backspace, enter, other) instead of one `None` group. It beat storing the real letter pairs (0.173 vs 0.212 at N=100) while storing no letters. Top-30 + kinds was 0.008 better but would store common letter pairs, so it was rejected for privacy.
- **README story:** changed from a university dorm to the real reason: I leave my PC on at home, I don't always press Win+L, and my brother uses it while I'm away. The brother is the catalyst; the README scales the idea to any open session (offices, hospitals, labs). Every detail in it is true.
- **Quarantine before storing live typing:** records are stored only after every window that judged them looked like me, and dropped on a lock. The keep threshold is separate from the lock threshold, because losing some of my own typing is cheap and a false lock is not.
- **Tests under pytest without rewriting them:** one pytest file runs each check script as its own case, so the scripts still run on their own. Live keyboard demos were renamed `*_demo.py` so no test pattern can pick them up.
- **Roommate as tester:** standing consent to type as the impostor; their typing only goes into separate test databases, never into my profile, and is deleted on request.
- **License:** MIT.
- **Commits:** Conventional Commits style, with no AI attribution lines.

### Open items
- Keep collecting my own typing (rough target: 20,000 records over at least 7 days; 1,544 so far).
- Tune the lock threshold, grace and keep threshold on my data, against at most 1 false lock per day; check that quarantine does not narrow my profile over time.
- Real `--lock` test with my roommate as the impostor; then make the repo public (end of Milestone 1).
- Even the best Aalto EER (0.165–0.173 at 100 records) is too high to lock on by itself, and Aalto is one session at 1 ms resolution: these are not Doppel accuracy numbers. The new scorer catches far more impostors on Aalto; whether it allows a low enough threshold for 1 false lock per day can only be measured on my data.

---

## 2026-09-30: Keyboard labels, collector, live listener and encrypted storage

### Built
- `src/doppel/keymap.py`: each letter gets an (x, y) position on a QWERTY keyboard. `relation(prev_key, key)` returns a coarse label: (same half of the keyboard?, distance bucket 0-3).
- `src/doppel/records.py`: `KeystrokeRecord`, a read-only dataclass (label, hold_ms, dd_ms, ud_ms).
- `src/doppel/collector.py`: `KeystrokeCollector` turns key events into one record per pair of consecutive presses. It handles auto-repeat, overlapping keys (`pending`), and skips pairs more than 2 s apart.
- `src/doppel/listener.py`: pynput listener that feeds the collector and passes records to a callback (`on_record`).
- `src/doppel/keystore.py`: 256-bit AES-GCM key, protected with Windows DPAPI and stored as a blob in the git-ignored `data/` folder.
- `src/doppel/storage.py`: `RecordStore` buffers 200 records, shuffles them, encrypts the batch with AES-GCM and writes one SQLite row (day, nonce, data).
- Test scripts with hand-worked expected values: `relation_test.py`, `records_test.py`, `collector_test.py`, `keystore_test.py`, `storage_test.py`. All pass.
- Turned on Pylance type checking (basic) and added type hints where it flagged problems.

### Roadblock 1: Finger-based labels didn't match how people actually type

**Problem:** The first plan labelled digraphs by finger (same finger / same hand / alternating hands), using a textbook touch-typing table. I use my ring finger for `q a z` and `p`, so the table was wrong for me, and it would be wrong for anyone who doesn't touch type.

**Process:**
- Switched to labels based on keyboard geometry, which make no assumption about the typist: whether the two keys are on the same half, and how far apart they are (straight-line distance, in key widths, with row stagger).
- Distance is a hypothesis about what affects timing (Fitts's law: longer reaches take longer), not a guarantee. Plan: compare no label, finger labels and position labels on the Aalto free-text dataset and keep whichever earns its place.

**Result:** `relation()` passed 7 hand-checked cases, including uppercase letters, a double letter ("ll" → same key) and a non-letter key (→ None).

### Roadblock 2: A collector bug that produced plausible but wrong numbers

**Problem:** In the overlap case I stored the pending pair under the key going down (`key`) instead of the key we were waiting for (`prev_key`). Nothing crashed and every number looked reasonable, but every overlapped record attached the wrong key's release.

**Process:** Made the collector take timestamps as arguments so it can be driven by scripted events, then wrote tests replaying sequences whose results I worked out by hand (no overlap, a three-key overlap, auto-repeat, a long pause, a double letter).

**Result:** The test showed the wrong values immediately. After the fix, all 5 collector checks pass. The three-key overlap produces h→e (hold 79, DD 9, UD -70) and t→h (hold 122, DD 35, UD -87), as calculated by hand.

### Roadblock 3: Calling a method that didn't exist

**Problem:** The listener crashed with `AttributeError: 'KeystrokeCollector' object has no attribute 'on_press'`. I had mixed up the listener's callback names (`on_press`, `on_release`) with the collector's methods (`key_down`, `key_up`).

**Process:** Learned to read a traceback: the last line says what went wrong, and the last frame in my own code says where. Turned on Pylance type checking, which underlines this kind of mistake before the code runs.

**Result:** The live listener works. In one test, fast "the" gave t→h with DD 42.3, hold 122.7 and UD -80.4 (42.3 - 122.7 = -80.4). The double l in "hello" gave label (True, 0), and the space gave label None.

### Roadblock 4: Two privacy leaks found during design

**Problem:**
1. Records stored in typing order leak word lengths: the None labels mostly mark spaces, so the counts of letter records between them would read as word lengths (for example "3, 5, 2, 4").
2. Fernet tokens contain their creation time in plain form, to the second. One token per batch would leave a timeline of when I typed.

**Process:**
- Each batch of 200 records is shuffled with the OS's cryptographic randomness (`secrets.SystemRandom`) before encryption, so order is lost.
- Switched from Fernet to AES-GCM, which has no timestamp. Each batch gets a fresh random 12-byte nonce.
- The date (day only) is the only unencrypted value. It's passed to AES-GCM as associated data, so changing it is detected.

**Result:** `storage_test.py` confirms the round trip returns the same records, the file contains no readable timings, a wrong key fails, and changing a row's date fails with `InvalidTag`. `keystore_test.py` confirms a single changed ciphertext byte is detected.

### Design decisions
- **Key storage:** DPAPI through `pywin32`, so the key never sits in plain form on disk and is tied to my Windows login. It protects against copied files or a stolen drive. It does not protect against anything running as me while I'm logged in. Risk: if an admin resets my password, the key can become unrecoverable.
- **One encrypted batch per row** instead of per-record rows (row count reveals little) or SQLCipher (fragile native dependency on Windows for little extra benefit).
- **Batch size 200:** more mixing per batch, at most one batch lost on a crash. The buffer is also saved on exit.
- **Retention:** store dates now and decide the deletion rule once I know how much data training needs.
- **JSON** inside the encrypted batch, since it's readable once decrypted and size doesn't matter here.
- **Threat model sketch:** a roommate at my unlocked laptop is stopped by detection and lock (time-to-lock is the key number). A thief with my files is stopped by encryption. Malware running as me is out of scope. Known gaps: someone can kill the app, or not type at all.

### Open items
- Background writer thread for storage, so encryption and disk writes never run inside the keyboard callbacks. Measure how long one flush takes.
- Connect storage to the live listener.
- Scorer interface and the privacy/threat-model doc.

---

## 2026-09-29: Setup and the raw keyboard measurements

### Built
- Repo and `uv` project (`src/doppel/` package layout), pushed to GitHub (private for now).
- `.gitignore` covering `data/`, `exports/`, `*.db`, `*.sqlite`, `*.key` and `.env` *before* any data existed.
- `scripts/hook_test.py`: raw pynput listener printing down/up events with gaps between them (no key names).
- `scripts/hold_test.py`: correct hold times.
- `scripts/flight_test.py`: hold, DD (down-to-down) and UD (up-to-down) for every real keypress, including overlapping keys.

### Key concepts
- Hold = key up minus key down. DD = next key's down minus this key's down. UD = next key's down minus this key's up.
- Identity check: `UD = DD - hold(previous key)`. Verified on my own output (for example 146.4 - 68.6 = 77.8).
- UD goes negative when keys overlap (the next key goes down before the previous one is released). That is normal and is a useful feature.

### Roadblock 1: Holding a key produced fake keystrokes

**Problem:** Holding one key for about 0.8 s produced 10 key-down events but only 1 key-up, so any code that assumes down and up alternate would count 10 keystrokes and give wrong hold and flight times.

**Process:**
- Logged raw events (`hook_test.py`) and saw the pattern: one real down, a ~500 ms pause, then repeated downs about 31 ms apart.
- Considered ignoring a key if it matches the previous key, but that breaks double letters like "ll", which are two real presses.
- Chose to track the keys currently held in a dictionary. A down for a key already in `held` is an auto-repeat, so it is ignored.

**Result:** Holding a key now produces 1 hold measurement (1604.2 ms in my test) and no extra flight times, instead of about 10 fake events.

### Roadblock 2: Overlapping keys gave wrong UD values

**Problem:** Fast typing overlaps keys (down, down, up, up). My first UD code kept a single `last_up` value, which is overwritten by whichever key was released last. With three overlapping keys (release order h, t, e), it attached the wrong release to the wrong pair.

**Process:**
- Derived the identity `UD = DD - hold(previous key)` and used it as a checker on my own output.
- Considered computing UD from that identity, but the previous key's hold is not known yet in an overlap, so the waiting problem is the same either way.
- Chose a `pending` dictionary: when the previous key is still held at the next press, store the next press time under the previous key. Finish the UD when that specific key is released.
- Found a second bug on the way: saving `held[key]` before the check made double letters ("ll") look like an overlap. Fixed by saving it last.

**Result:** On a fast "the" the output was UD = -26.3 ms (h to e) and -87.1 ms (t to h). Both match `DD - hold` (44.0 - 70.3 and 34.9 - 122.0). The same check held on every pair in slow and fast "hello", within 0.1 ms of rounding.

### Roadblock 3: Windows blocked the project launcher

**Problem:** `uv run doppel` failed with "An Application Control policy has blocked this file" (os error 4551), because Smart App Control blocks unsigned `.exe` files.

**Process:** Did not disable Smart App Control, since it cannot be re-enabled without reinstalling Windows. Added `src/doppel/__main__.py` and ran the package as `uv run python -m doppel` instead.

**Result:** The project runs without an `.exe`. The same restriction will apply to the PyInstaller build, so I will document it as "unsigned" in the README.

### Design decisions (privacy)
- Key identities exist in memory only while the key is held, and `.pop()` erases them on release. Nothing prints or stores which key it was.
- Digraphs will be labelled by finger relation (same finger / same hand / alternating hands), not by letters. Hashing keys would not help because there are only about 100 keys to brute-force.
- Finger relation is a privacy choice, not the research default (most papers use the actual key pairs). It will likely cost some accuracy, and I plan to measure how much.
- Store record order or a coarse time bucket, not exact timestamps, so rows cannot be lined up with what I was doing.

### Open items
- `src/doppel/keymap.py`: QWERTY finger map plus `relation(prev_key, key)`.
- Then the encrypted SQLite schema, the scorer interface sketch, and the 1-page privacy/threat-model doc.
- Later: compare finger-relation labels against real key pairs on the CMU data to measure what privacy costs in accuracy.
