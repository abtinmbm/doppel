# Doppel.exe Devlog

One entry per work session: what I built, what broke, what I learned, and what's still open.
Newest entry at the top. Only put numbers here that I actually measured.

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
