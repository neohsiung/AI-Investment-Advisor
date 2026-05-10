"""
scripts/reseed_all_forensic.py
==============================
Forensic reseed script — writes user settings back to the DB from env variables.

IMPORTANT: This script requires environment variables for all sensitive values.
           NEVER hardcode secrets. Use a .env file or inject from your secrets manager.

Usage (inside container):
    docker exec advisor_prod_api python scripts/reseed_all_forensic.py

Required env vars:
    RESEED_USER_ID              - Target user UUID
    RESEED_FRED_API_KEY         - FRED API key
    RESEED_VANTAGE_API_KEY      - Alpha Vantage API key
    RESEED_FINNHUB_API_KEY      - Finnhub API key
    RESEED_TIINGO_API_KEY       - Tiingo API key
    RESEED_OPENROUTER_API_KEY   - OpenRouter API key (sk-or-v1-...)
    RESEED_NVIDIA_API_KEY       - NVIDIA NIM API key (nvapi-...)
    RESEED_TELEGRAM_BOT_TOKEN   - Telegram bot token
    RESEED_TELEGRAM_CHAT_ID     - Telegram chat ID
    RESEED_ETORO_TOKEN          - eToro JWT token
    RESEED_NGROK_URL            - ngrok public URL
    DB_URL                      - PostgreSQL connection URL
"""
import psycopg2
import json
import os
import sys


def reseed():
    db_url = os.environ.get("DB_URL", "postgresql://postgres:postgres@advisor_prod_db:5432/advisor_prod")
    user_id = os.environ.get("RESEED_USER_ID")

    if not user_id:
        print("❌ ERROR: RESEED_USER_ID env var is required.", file=sys.stderr)
        sys.exit(1)

    settings = {
        "fred_api_key":                    os.environ.get("RESEED_FRED_API_KEY", ""),
        "vantage_api_key":                 os.environ.get("RESEED_VANTAGE_API_KEY", ""),
        "finnhub_api_key":                 os.environ.get("RESEED_FINNHUB_API_KEY", ""),
        "tiingo_api_key":                  os.environ.get("RESEED_TIINGO_API_KEY", ""),
        "openrouter_api_key":              os.environ.get("RESEED_OPENROUTER_API_KEY", ""),
        "nvidia_api_key":                  os.environ.get("RESEED_NVIDIA_API_KEY", ""),
        "notification_telegram_bot_token": os.environ.get("RESEED_TELEGRAM_BOT_TOKEN", ""),
        "notification_telegram_chat_id":   os.environ.get("RESEED_TELEGRAM_CHAT_ID", ""),
        "etoro_token":                     os.environ.get("RESEED_ETORO_TOKEN", ""),
        "ngrok_url":                       os.environ.get("RESEED_NGROK_URL", ""),
        "etoro_api_base_url":              "http://advisor_prod_api:8000",
    }

    missing = [k for k, v in settings.items() if not v and k != "etoro_api_base_url"]
    if missing:
        print(f"⚠️  WARNING: Missing env vars for: {', '.join(missing)}")
        print("   Those settings will be set to empty string in the DB.")

    conn = psycopg2.connect(db_url)
    cur = conn.cursor()

    print("--- Reseeding Settings ---")
    for key, value in settings.items():
        cur.execute("""
            INSERT INTO settings (user_id, key, value, updated_at)
            VALUES (%s, %s, %s, NOW())
            ON CONFLICT (user_id, key) DO UPDATE SET value = EXCLUDED.value;
        """, (user_id, key, json.dumps(value)))
        print(f"  ✓ {key}")

    print("\n--- Updating LLM Providers ---")
    provider_updates = [
        ("ollama",       "http://shared_ollama:11434/v1"),
        ("nvidia",       "https://integrate.api.nvidia.com/v1"),
        ("openrouter",   "https://openrouter.ai/api/v1"),
    ]

    for code, url in provider_updates:
        cur.execute("""
            UPDATE llm_providers
            SET base_url = %s, enabled = True
            WHERE provider_code = %s AND user_id = %s;
        """, (url, code, user_id))
        print(f"  ✓ {code} -> {url}")

    conn.commit()
    cur.close()
    conn.close()
    print("\n✓ Reseed completed successfully.")


if __name__ == "__main__":
    reseed()
