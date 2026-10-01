"""Doppel.exe: continuous authentication from how the owner uses the laptop.

Modules:
    keymap    - key identity (Windows virtual key codes) and the keyboard
                geometry label for a pair of keys
    records   - KeystrokeRecord, the timings for one pair of key presses
    collector - turns key-down/key-up events into KeystrokeRecords
    listener  - live keyboard hook that feeds the collector
    keystore  - AES-GCM database key, protected with Windows DPAPI
    storage   - shuffled, encrypted batches of records in SQLite

main() is a placeholder entry point that only prints a greeting.
"""


def main() -> None:
    """Placeholder entry point: print a greeting."""
    print("Hello from doppel!")
