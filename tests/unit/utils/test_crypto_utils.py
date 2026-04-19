import pytest
import os
from unittest.mock import patch, MagicMock

from src.utils.crypto_utils import encrypt_secret, decrypt_secret, _FERNET

def test_encrypt_decrypt_secret():
    plain_text = "test_super_secret_api_key_123"
    
    # Encrypt
    encrypted = encrypt_secret(plain_text)
    assert encrypted != plain_text
    assert len(encrypted) > len(plain_text)
    
    # Decrypt
    decrypted = decrypt_secret(encrypted)
    assert decrypted == plain_text

def test_encrypt_secret_empty():
    assert encrypt_secret("") == ""
    assert encrypt_secret(None) == ""

def test_decrypt_secret_empty():
    assert decrypt_secret("") == ""
    assert decrypt_secret(None) == ""

def test_encrypt_exception():
    with patch("src.utils.crypto_utils._FERNET.encrypt") as mock_encrypt:
        mock_encrypt.side_effect = Exception("Encryption failed")
        
        # fallback returns plain text
        assert encrypt_secret("some_secret") == "some_secret"

def test_decrypt_exception():
    with patch("src.utils.crypto_utils._FERNET.decrypt") as mock_decrypt:
        mock_decrypt.side_effect = Exception("Decryption failed")
        
        # fallback returns cipher text
        assert decrypt_secret("invalid_cipher_text") == "invalid_cipher_text"
