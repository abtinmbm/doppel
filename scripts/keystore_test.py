"""Checks for doppel.keystore and a first look at AES-GCM.

Creates a key in a temporary file, loads it back, confirms the file does not
contain the plain key, then encrypts and decrypts a message with AES-GCM and
shows that tampering with the ciphertext is detected.
Run from the project folder, since the key path is relative.
"""

import os
from pathlib import Path

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from doppel.keystore import get_or_create_key

path = Path("data") / "test_key.dpapi"
path.unlink(missing_ok=True)  # start fresh

# The first call creates the key; the second loads the same key back.
key1 = get_or_create_key(path)
key2 = get_or_create_key(path)
assert key1 == key2
assert len(key1) == 32  # 256 bits

# The file holds the DPAPI-protected blob, not the plain key.
assert key1 not in path.read_bytes()

# AES-GCM: each message gets a fresh random 12-byte nonce, stored with it.
aes = AESGCM(key1)
nonce = os.urandom(12)
ciphertext = aes.encrypt(nonce, b"hello", None)
assert b"hello" not in ciphertext
assert aes.decrypt(nonce, ciphertext, None) == b"hello"

# Changing a single byte of the ciphertext makes decryption fail.
tampered = bytes([ciphertext[0] ^ 1]) + ciphertext[1:]
try:
    aes.decrypt(nonce, tampered, None)
    raise AssertionError("tampering should be detected")
except InvalidTag:
    pass

path.unlink()  # clean up the test key
print("All keystore checks passed.")
