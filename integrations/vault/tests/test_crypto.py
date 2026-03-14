"""Tests for AES-256-GCM encryption module."""

import pytest
from cryptography.exceptions import InvalidTag

from integrations.vault.crypto import decrypt, encrypt


class TestEncryptDecrypt:
    """Round-trip and security tests for crypto module."""

    def test_round_trip(self) -> None:
        """Encrypted value decrypts back to original plaintext."""
        secret = "test-master-secret-1234"
        plaintext = "my-super-secret-spid-credentials"

        ciphertext, salt = encrypt(plaintext, secret, iterations=1000)
        result = decrypt(ciphertext, salt, secret, iterations=1000)

        assert result == plaintext

    def test_different_salt_per_encryption(self) -> None:
        """Two encryptions of the same value produce different ciphertexts."""
        secret = "test-master-secret-1234"
        plaintext = "same-value"

        ciphertext1, salt1 = encrypt(plaintext, secret, iterations=1000)
        ciphertext2, salt2 = encrypt(plaintext, secret, iterations=1000)

        assert ciphertext1 != ciphertext2
        assert salt1 != salt2

        # Both decrypt to the same value
        assert decrypt(ciphertext1, salt1, secret, iterations=1000) == plaintext
        assert decrypt(ciphertext2, salt2, secret, iterations=1000) == plaintext

    def test_wrong_key_raises(self) -> None:
        """Decryption with wrong master secret raises InvalidTag."""
        correct_secret = "correct-secret"
        wrong_secret = "wrong-secret"
        plaintext = "sensitive-data"

        ciphertext, salt = encrypt(plaintext, correct_secret, iterations=1000)

        with pytest.raises(InvalidTag):
            decrypt(ciphertext, salt, wrong_secret, iterations=1000)

    def test_empty_string(self) -> None:
        """Empty string can be encrypted and decrypted."""
        secret = "test-secret"
        ciphertext, salt = encrypt("", secret, iterations=1000)
        assert decrypt(ciphertext, salt, secret, iterations=1000) == ""

    def test_unicode_content(self) -> None:
        """Unicode content (Italian characters) round-trips correctly."""
        secret = "test-secret"
        plaintext = "Credenziale SPID per l'Agenzia delle Entrate — configurazione è completa"
        ciphertext, salt = encrypt(plaintext, secret, iterations=1000)
        assert decrypt(ciphertext, salt, secret, iterations=1000) == plaintext
