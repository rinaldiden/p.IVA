"""AES-256-GCM encryption with PBKDF2-HMAC-SHA256 key derivation."""

import hashlib
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM


def derive_key(master_secret: str, salt: bytes, iterations: int = 100_000) -> bytes:
    """Derive a 256-bit key from master secret and per-record salt using PBKDF2."""
    return hashlib.pbkdf2_hmac(
        "sha256",
        master_secret.encode("utf-8"),
        salt,
        iterations,
        dklen=32,
    )


def encrypt(plaintext: str, master_secret: str, iterations: int = 100_000) -> tuple[bytes, bytes]:
    """Encrypt plaintext with AES-256-GCM.

    Returns:
        (ciphertext, salt) — salt is unique per encryption, making identical
        plaintexts produce different ciphertexts.
    """
    salt = os.urandom(16)
    key = derive_key(master_secret, salt, iterations)
    aesgcm = AESGCM(key)
    nonce = os.urandom(12)
    ciphertext = aesgcm.encrypt(nonce, plaintext.encode("utf-8"), None)
    # Prepend nonce to ciphertext for storage
    return nonce + ciphertext, salt


def decrypt(encrypted_value: bytes, salt: bytes, master_secret: str, iterations: int = 100_000) -> str:
    """Decrypt AES-256-GCM ciphertext.

    Args:
        encrypted_value: nonce (12 bytes) + ciphertext
        salt: per-record salt used during encryption
        master_secret: master secret for key derivation

    Returns:
        Decrypted plaintext string.

    Raises:
        cryptography.exceptions.InvalidTag: if key is wrong or data is tampered.
    """
    key = derive_key(master_secret, salt, iterations)
    nonce = encrypted_value[:12]
    ciphertext = encrypted_value[12:]
    aesgcm = AESGCM(key)
    return aesgcm.decrypt(nonce, ciphertext, None).decode("utf-8")
