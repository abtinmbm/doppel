# Doppel.exe Devlog

One entry per work session: what I built, what broke, what I learned, and what's next.
Newest entry at the top. Only put numbers here that I actually measured.

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

### Next
- `src/doppel/keymap.py`: QWERTY finger map plus `relation(prev_key, key)`.
- Then the encrypted SQLite schema, the scorer interface sketch, and the 1-page privacy/threat-model doc.
- Midterms Oct 21-27, reading week Oct 9-18: finish the collector before Oct 9, pause Doppel during midterms, resume the CMU model after Oct 27.
- Later: compare finger-relation labels against real key pairs on the CMU data to measure what privacy costs in accuracy.
