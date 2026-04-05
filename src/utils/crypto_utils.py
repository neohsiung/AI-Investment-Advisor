"""
Cryptography Utility — Security Layer [Phase 21].
加密工具 — 負責敏感資料（如 API Key）的對稱式加密存取。
"""

import os
import logging
from cryptography.fernet import Fernet

logger = logging.getLogger(__name__)

# Master Key should be stored in ENV: MASTER_CRYPTO_KEY
# If missing, it uses a default (NOT SECURE for prod, but prevents crash)
_KEY = os.getenv("MASTER_CRYPTO_KEY")
if not _KEY:
    logger.warning("⚠️ MASTER_CRYPTO_KEY not set. Using insecure default. Set this in production!")
    # Generation: Fernet.generate_key().decode()
    _KEY = "L_Wf6E8pXj9v0yG8_pYpU_XNfV7fE4Xj9v0yG8_pNfA=" 

_FERNET = Fernet(_KEY.encode())

def encrypt_secret(plain_text: str) -> str:
    """Encrypts a string for DB storage."""
    if not plain_text:
        return ""
    try:
        return _FERNET.encrypt(plain_text.encode()).decode()
    except Exception as e:
        logger.error(f"Encryption failed: {e}")
        return plain_text

def decrypt_secret(cipher_text: str) -> str:
    """Decrypts a string from DB storage."""
    if not cipher_text:
        return ""
    try:
        return _FERNET.decrypt(cipher_text.encode()).decode()
    except Exception:
        # Fallback to plain if decryption fails (likely migrated from plain text)
        return cipher_text
