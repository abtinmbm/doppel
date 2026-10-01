"""Creates and loads the encryption key for Doppel's database.

The database is encrypted with a 256-bit AES-GCM key. That key is never
written to disk in plain form: it is protected with Windows DPAPI, which
encrypts it using a secret tied to the current Windows user account.

How it works:
    1. On first run, a random AES key is generated, protected with
       CryptProtectData, and the protected blob is written to the key file.
    2. On later runs, the blob is read and CryptUnprotectData recovers the key.
    3. The plain key exists only in memory.

Security notes:
    - Only the same Windows user on the same machine can unprotect the key,
      so copying the data folder to another account or machine is not enough
      to read the database.
    - Any program running as this user can also unprotect the key.
    - If the key file is lost, or the user's DPAPI secrets become unavailable
      (for example after an administrator resets the account password), the
      database cannot be decrypted.
"""

from pathlib import Path

import win32crypt
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

# Location of the DPAPI-protected key, inside the git-ignored data folder.
KEY_PATH = Path("data") / "db_key.dpapi"

# Stored alongside the protected blob by DPAPI. It is not secret.
DESCRIPTION = "Doppel database key"

# Tells DPAPI never to show a prompt; it fails instead.
CRYPTPROTECT_UI_FORBIDDEN = 0x1


def _protect(key: bytes) -> bytes:
    """Encrypt the key with DPAPI for the current Windows user."""
    return win32crypt.CryptProtectData(
        key, DESCRIPTION, None, None, None, CRYPTPROTECT_UI_FORBIDDEN
    )


def _unprotect(blob: bytes) -> bytes:
    """Recover the key from a DPAPI-protected blob.

    CryptUnprotectData returns (description, data); only the data is needed.
    """
    _description, key = win32crypt.CryptUnprotectData(
        blob, None, None, None, CRYPTPROTECT_UI_FORBIDDEN
    )
    return key


def get_or_create_key(path: Path = KEY_PATH) -> bytes:
    """Return the database key, creating and storing it on first use.

    Args:
        path: file holding the DPAPI-protected key.

    Returns:
        The 32-byte AES-GCM key.
    """
    # Later runs: load the protected key and unprotect it.
    if path.exists():
        blob = path.read_bytes()
        return _unprotect(blob)

    # First run: generate a new random key and store it protected.
    key = AESGCM.generate_key(bit_length=256)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(_protect(key))
    return key
