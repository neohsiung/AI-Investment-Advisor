"""
Tests for LLMCredentialCipher to improve coverage.
"""
import pytest
from unittest.mock import patch, MagicMock
from src.services.llm_credential_cipher import LLMCredentialCipher


class TestLLMCredentialCipherBasic:
    """Test basic encrypt/decrypt with fallback (no Fernet key)."""

    def setup_method(self):
        """Create cipher without Fernet key (uses fallback)."""
        with patch.dict("os.environ", {}, clear=False):
            # Ensure no LLM_CREDENTIAL_KEY in env
            import os
            os.environ.pop("LLM_CREDENTIAL_KEY", None)
            self.cipher = LLMCredentialCipher(key=None)

    def test_encrypt_none_returns_none(self):
        result = self.cipher.encrypt(None)
        assert result is None

    def test_encrypt_empty_returns_empty(self):
        result = self.cipher.encrypt("")
        assert result == ""

    def test_decrypt_none_returns_none(self):
        result = self.cipher.decrypt(None)
        assert result is None

    def test_decrypt_empty_returns_empty(self):
        result = self.cipher.decrypt("")
        assert result == ""

    def test_encrypt_decrypt_roundtrip_fallback(self):
        """Fallback B64H encrypt/decrypt roundtrip."""
        plaintext = "my-secret-api-key-12345"
        ciphertext = self.cipher.encrypt(plaintext)
        assert ciphertext is not None
        assert ciphertext.startswith("B64H:")
        decrypted = self.cipher.decrypt(ciphertext)
        assert decrypted == plaintext

    def test_decrypt_legacy_plain_string(self):
        """Legacy plain strings (no prefix) are returned as-is."""
        plain = "sk-legacy-key-no-prefix"
        result = self.cipher.decrypt(plain)
        assert result == plain

    def test_decrypt_b64h_malformed_no_dot(self):
        """B64H token without dot separator returns None."""
        malformed = "B64H:nodothere"
        result = self.cipher.decrypt(malformed)
        assert result is None

    def test_decrypt_b64h_invalid_base64(self):
        """B64H token with invalid base64 returns None."""
        invalid = "B64H:!!!invalid!!!.somemac"
        result = self.cipher.decrypt(invalid)
        assert result is None

    def test_mask_none_returns_none(self):
        result = self.cipher.mask(None)
        assert result is None

    def test_mask_empty_returns_empty(self):
        result = self.cipher.mask("")
        assert result == ""

    def test_mask_short_key(self):
        """Keys <= 8 chars are fully masked."""
        plaintext = "short"
        ciphertext = self.cipher.encrypt(plaintext)
        masked = self.cipher.mask(ciphertext)
        assert masked == "*****"

    def test_mask_long_key(self):
        """Keys > 8 chars show first 3 and last 4."""
        plaintext = "sk-abcdefghijklmnop"
        ciphertext = self.cipher.encrypt(plaintext)
        masked = self.cipher.mask(ciphertext)
        assert masked.startswith("sk-")
        assert masked.endswith("mnop")
        assert "****" in masked

    def test_mask_plain_legacy_key(self):
        """Masking a plain (legacy) key works."""
        plain = "sk-verylonglegacykey1234"
        masked = self.cipher.mask(plain)
        assert "****" in masked

    def test_encrypt_with_custom_key(self):
        """Cipher with custom key uses fallback if not valid Fernet key."""
        cipher = LLMCredentialCipher(key="not-a-valid-fernet-key")
        ciphertext = cipher.encrypt("test-value")
        assert ciphertext is not None
        decrypted = cipher.decrypt(ciphertext)
        assert decrypted == "test-value"


class TestLLMCredentialCipherFernet:
    """Test Fernet encrypt/decrypt when cryptography is available."""

    def test_fernet_encrypt_decrypt_roundtrip(self):
        """Test Fernet roundtrip if cryptography is installed."""
        try:
            from cryptography.fernet import Fernet
            key = Fernet.generate_key().decode("utf-8")
            cipher = LLMCredentialCipher(key=key)
            plaintext = "fernet-secret-key-xyz"
            ciphertext = cipher.encrypt(plaintext)
            assert ciphertext is not None
            assert ciphertext.startswith("FERN:")
            decrypted = cipher.decrypt(ciphertext)
            assert decrypted == plaintext
        except ImportError:
            pytest.skip("cryptography not installed")

    def test_fernet_decrypt_fern_token_without_fernet_returns_none(self):
        """If Fernet not initialized, decrypting FERN: token returns None."""
        cipher = LLMCredentialCipher(key=None)
        # Force no fernet
        cipher._fernet = None
        result = cipher.decrypt("FERN:sometoken")
        assert result is None

    def test_fernet_decrypt_invalid_token_returns_none(self):
        """Invalid Fernet token returns None."""
        try:
            from cryptography.fernet import Fernet
            key = Fernet.generate_key().decode("utf-8")
            cipher = LLMCredentialCipher(key=key)
            result = cipher.decrypt("FERN:invalidtoken")
            assert result is None
        except ImportError:
            pytest.skip("cryptography not installed")

    def test_try_build_fernet_empty_key_returns_none(self):
        """Empty key returns None from _try_build_fernet."""
        result = LLMCredentialCipher._try_build_fernet("")
        assert result is None

    def test_mask_undecryptable_returns_stars(self):
        """If decrypt returns empty, mask returns ****."""
        cipher = LLMCredentialCipher(key=None)
        # Patch decrypt to return empty
        with patch.object(cipher, "decrypt", return_value=""):
            result = cipher.mask("some-ciphertext")
            assert result == "****"
