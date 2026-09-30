\# Doppel.exe Devlog



One entry per work session: what I built, what broke, what I learned, and what's next.

Only put numbers here that I actually measured.



\---



\## 2026-09-29: Setup and the raw keyboard measurements



\*\*Built\*\*

\- Repo and `uv` project (`src/doppel/` package layout), pushed to GitHub (private for now).

\- `.gitignore` covering `data/`, `exports/`, `\*.db`, `\*.sqlite`, `\*.key` and `.env` \*before\* any data existed.

\- `scripts/hook\_test.py`: raw pynput listener printing down/up events with gaps between them (no key names).

\- `scripts/hold\_test.py`: correct hold times.

\- `scripts/flight\_test.py`: hold, DD (down-to-down) and UD (up-to-down) for every real keypress, including overlapping keys.



\*\*Key concepts\*\*

\- Hold = key up minus key down. DD = next key's down minus this key's down. UD = next key's down minus this key's up.

\- Identity check: `UD = DD - hold(previous key)`. Verified on my own output (for example 146.4 - 68.6 = 77.8).

\- UD goes negative when keys overlap (the next key goes down before the previous one is released). That is normal and is a useful feature.



\*\*Problems and fixes\*\*

\- \*Smart App Control blocked `uv run doppel`\* (os error 4551): the generated `.exe` launcher is unsigned. Fixed by adding `\_\_main\_\_.py` and running `uv run python -m doppel`. Expect the same issue with the PyInstaller `.exe` later.

\- \*Auto-repeat:\* holding a key sent about 10 fake key-downs. Fixed by ignoring a down if that key is already in `held`.

\- \*Overlap:\* a single `last\_up` variable gives the wrong UD when three keys overlap (release order h, t, e). Fixed with a `pending` dictionary that finishes each UD when the right key is released.

\- \*Double letters ("ll"):\* saving `held\[key]` before checking `prev in held` made the previous key look still held. Fixed by moving the save to the end of `on\_press`.



\*\*Design decisions (privacy)\*\*

\- Key identities exist in memory only while the key is held, and `.pop()` erases them on release. Nothing prints or stores which key it was.

\- Digraphs will be labelled by finger relation (same finger / same hand / alternating hands), not by letters. Hashing keys would not help because there are only about 100 keys to brute-force.

\- Store record order or a coarse time bucket, not exact timestamps, so rows cannot be lined up with what I was doing.



\*\*Next\*\*

\- `src/doppel/keymap.py`: QWERTY finger map plus `relation(prev\_key, key)`.

\- Then the encrypted SQLite schema, the scorer interface sketch, and the 1-page privacy/threat-model doc.

