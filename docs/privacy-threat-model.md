# Doppel.exe: Privacy and Threat Model

One page: what Doppel protects, from whom, how, and what it does not stop.

## What needs protecting

| Asset | Where it lives | Why it matters |
|---|---|---|
| The owner's open Windows session | Live, in memory | The thing Doppel exists to guard |
| What the owner types (text, passwords) | Never stored; key codes only in memory while a key is held, and the last key until the next press | A keystroke tool must not become a keylogger |
| Typing-timing records | `data/doppel.db`, encrypted | Biometric data; also the owner's profile, so tampering with it weakens detection |
| The database key | `data/db_key.dpapi`, DPAPI-protected | Whoever holds it can read the records |
| Other people's typing | Only in separate test databases, with consent | Their biometric data, collected without their knowledge otherwise |

## Attackers

| Attacker | Has | Goal | Doppel's response |
|---|---|---|---|
| **Person at the unlocked PC** (the brother) | Keyboard and screen of the live session | Use the session | Typing scorer → trust engine → `LockWorkStation`. After a quiet period, evidence expires and the first low trust value locks |
| **Same person, long term** | Repeated access before each lock | Poison the profile so their typing is accepted | Quarantine: live records are stored only if every window that judged them looked like the owner; everything pending is dropped on a lock |
| **Thief / file copier** | `data/` folder, backups | Read the timing data | AES-GCM per batch, key protected by DPAPI (tied to the owner's Windows login); batches shuffled, so even decrypted data has no typing order |
| **Software replay** | Code running in the session | Fake the owner's rhythm | Planned: reject injected events (`LLKHF_INJECTED`) |
| **Malware running as the owner** | Everything the owner has | Anything | **Out of scope.** It could log keys directly or decrypt via DPAPI |

## Privacy rules (enforced in code)

1. **No key identities on disk.** A record is a coarse label + hold, DD, UD. Letter pairs get keyboard geometry `(same_half, distance_bucket)`; others get key kinds such as `("right", "space")`. Chosen by experiment: on Aalto this label beat storing real letter pairs.
2. **No typing order.** Each 200-record batch is shuffled with the OS cryptographic RNG before encryption, so label sequences cannot reveal word lengths.
3. **Encrypted at rest.** AES-GCM, fresh 12-byte nonce per batch. The only plaintext field is the day, bound as associated data so changing it is detected. Not Fernet: its tokens carry a plaintext timestamp to the second.
4. **No network calls.** Everything stays local.
5. **Consent for others' data.** Impostor typing goes only to clearly named test databases, never into the owner's profile, never committed, deleted on request.
6. **Writing style is offline only.** No live text capture: a rolling text buffer would hold passwords. Experiments use text the owner exports on purpose, kept out of the repository.

## What still leaks or gets through

- **Typing volume per day is visible without the key.** The plaintext day column and the row count let anyone with the file read roughly how much the owner typed each day (to within one 200-record batch).
- **Decrypted label counts give coarse statistics.** For example, the number of space pairs approximates the number of words typed. The content stays hidden.
- **The app can be killed.** Anyone at the session can end the Python process in Task Manager (a watchdog is optional future work).
- **Passive use is invisible.** Reading or scrolling without typing produces no typing evidence; a mouse signal is planned.
- **Everything before the lock gets through.** The measure of this is keystrokes-until-lock.
- **Poisoning resistance is capped by the detector.** An impostor the scorer cannot tell apart from the owner passes the quarantine as well.
- **Hardware replay** (a USB device acting as a keyboard) is not flagged by Windows; it needs statistical defenses.
- **DPAPI limits.** Someone with the files *and* the owner's Windows password can decrypt offline. An administrator password reset can make the key unrecoverable (records lost, nothing leaked).
- **Memory.** Held key codes and the last key code exist briefly in process memory; malware could read them (out of scope, as above).
- **Lock-out risk to the owner.** A false lock costs the owner a password, PIN or face unlock. The target is at most one false lock per day, which sets the threshold and grace.

## Why not just...

- **Idle lock?** The attacker sits down inside the idle window.
- **Dynamic Lock?** The owner's phone is still on the desk.
- **BitLocker?** It protects a powered-off disk, not an open session, copied files or backups. Doppel's encryption is defense in depth for its own data.
