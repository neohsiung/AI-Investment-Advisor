"""
One-time migration: encrypt plaintext sensitive settings already in DB.
Run ONCE after APP_SECRET_KEY is set in .env.

Usage:
    python scripts/encrypt_existing_settings.py
"""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from dotenv import load_dotenv
load_dotenv()

from cryptography.fernet import Fernet
from sqlalchemy import text
from src.data.database import get_db_engine

SECRET_KEY = os.getenv("APP_SECRET_KEY")
if not SECRET_KEY:
    print("ERROR: APP_SECRET_KEY not set in .env. Aborting.")
    sys.exit(1)

cipher = Fernet(SECRET_KEY.encode())
SENSITIVE_PATTERNS = ["api_key", "token", "secret", "password", "private_key", "_pass"]

def should_encrypt(key: str) -> bool:
    return any(p in key.lower() for p in SENSITIVE_PATTERNS)

def already_encrypted(value: str) -> bool:
    return isinstance(value, str) and value.startswith("ENC:")

def encrypt(value: str) -> str:
    return f"ENC:{cipher.encrypt(value.encode()).decode()}"

engine = get_db_engine()

with engine.begin() as conn:
    rows = conn.execute(text("SELECT user_id, key, value FROM settings")).fetchall()

    migrated = 0
    for user_id, key, value in rows:
        if not should_encrypt(key):
            continue
        if not isinstance(value, str):
            continue
        if already_encrypted(value):
            continue
        encrypted = encrypt(value)
        conn.execute(
            text("UPDATE settings SET value = :v WHERE user_id = :u AND key = :k"),
            {"v": encrypted, "u": user_id, "k": key}
        )
        migrated += 1
        print(f"  Encrypted: {key} (user={user_id[:8]}...)")

print(f"\nDone. {migrated} values encrypted.")
