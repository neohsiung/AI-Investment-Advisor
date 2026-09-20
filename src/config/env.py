"""
Infrastructure environment variables, declared in one place.

Scope boundary — this file is NOT for business settings:

    settings table  (config/settings_schema.yaml)  business configuration
    this file       (.env)                          infrastructure + global brakes

The precedence the project settled on (2026-08-23) is: settings table > .env >
code defaults. TRADING_MODE is the one deliberate inversion — it lives in .env
and overrides the table on purpose, so a global trading brake cannot be
defeated from the UI.

Before this model, ~70 env vars were read via bare `os.getenv()` calls scattered
across the codebase, each with its own inline default, and `.env.example`
documented six of them. There was no list of what the application actually
reads.

This is intentionally a *declaration*, not a replacement: existing `os.getenv`
call sites keep working. The value is that `EnvSettings.model_fields` is now an
enumerable inventory, which `tests/unit/config/test_env_documented.py` uses to
prove `.env.example` cannot silently fall behind.

本檔僅涵蓋基礎設施層變數，業務設定在 settings 表（見 settings_schema.yaml）。
先前 ~70 個變數散落在各處的 os.getenv 呼叫中、各自帶預設值，而 .env.example
只記錄了六個。此模型不取代既有呼叫，而是提供可列舉的清單以防文件漂移。
"""
from __future__ import annotations

from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class EnvSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",          # the .env legitimately carries more than this
        case_sensitive=True,
    )

    # ── Identity ─────────────────────────────────────────────────────────
    OWNER_ID: Optional[str] = Field(None, description="Pins the single owner's UUID")
    OWNER_EMAIL: Optional[str] = Field(None, description="Email used when bootstrapping the owner")
    PRIMARY_USER_ID: Optional[str] = Field(None, description="Legacy alias for OWNER_ID")
    USER_ID: Optional[str] = Field(None, description="Legacy alias for OWNER_ID")

    # ── Access control ───────────────────────────────────────────────────
    AUTH_MODE: str = Field("none", description="none | token")
    ADMIN_TOKEN: Optional[str] = Field(None, description="Required when AUTH_MODE=token")
    ALLOW_INSECURE_BIND: Optional[str] = Field(None, description="Override the non-loopback bind refusal")
    FRONTEND_ORIGIN: Optional[str] = Field(None, description="Comma-separated CORS allow-list")

    # ── Database ─────────────────────────────────────────────────────────
    DB_URL: Optional[str] = Field(None, description="Full SQLAlchemy URL; overrides the parts below")
    DB_HOST: str = Field("postgres", description="Postgres host")
    DB_PORT: str = Field("5432", description="Postgres port")
    DB_USER: str = Field("postgres", description="Postgres user")
    DB_PASS: Optional[str] = Field(None, description="Postgres password (compose requires it)")
    DB_NAME: str = Field("advisor_prod", description="Postgres database name")

    # ── Redis ────────────────────────────────────────────────────────────
    REDIS_URL: str = Field("redis://redis:6379/0", description="Celery broker and cache")
    REDIS_PASSWORD: Optional[str] = Field(None, description="Redis password")
    QUEUE_REDIS_URL: Optional[str] = Field(None, description="Separate queue Redis, if any")

    # ── Encryption ───────────────────────────────────────────────────────
    # These encrypt rows INSIDE Postgres. Regenerating them against an existing
    # database orphans every stored credential — see start.sh guard_encryption_keys.
    # 這兩把金鑰加密資料庫內容；對既有資料庫重新產生會讓憑證永久無法解密。
    APP_SECRET_KEY: Optional[str] = Field(None, description="Fernet key for settings values")
    LLM_CREDENTIAL_KEY: Optional[str] = Field(None, description="Fernet key for provider API keys")

    # ── Global trading brake ─────────────────────────────────────────────
    # Deliberately overrides the settings table. Note that `paper` is a full
    # stop here, not a degraded mode: the eToro token has no demo permission.
    # 刻意覆寫 settings 表；paper 在本專案是全停而非降級。
    TRADING_MODE: Optional[str] = Field(None, description="unset | live | paper")

    # ── Scheduling / cost ────────────────────────────────────────────────
    SENTINEL_TICK_CRON_MINUTE: str = Field("*/15", description="Sentinel tick cadence")
    BROKER_SYNC_CRON_MINUTE: str = Field("*/15", description="Broker position sync cadence")
    RSS_INGEST_CRON_MINUTE: str = Field("*/15", description="RSS ingest cadence")
    RSS_MAX_ENTRIES_PER_FEED: int = Field(3, description="Entries read per feed per run")
    RSS_MAX_EVENTS_PER_RUN: int = Field(10, description="Hard cap on analysis workflows per run")

    # ── Observability ────────────────────────────────────────────────────
    OTEL_EXPORTER_OTLP_ENDPOINT: Optional[str] = Field(None, description="Unset disables tracing")
    OTEL_SERVICE_NAME: Optional[str] = Field(None, description="Service name in traces")

    # ── Runtime ──────────────────────────────────────────────────────────
    NODE_ENV: Optional[str] = Field(None, description="`production` enables boot secret validation")
    HOST: Optional[str] = Field(None, description="Bind address (checked by assert_safe_bind)")
    OLLAMA_BASE_URL: Optional[str] = Field(None, description="Local Ollama endpoint")
    EMBED_MODEL: Optional[str] = Field(None, description="Embedding model name")
    COMPOSE_PROJECT_NAME: Optional[str] = Field(None, description="Docker compose project name")
    NGROK_AUTHTOKEN: Optional[str] = Field(None, description="ngrok auth token (tunnel profile)")
    NGROK_DOMAIN: Optional[str] = Field(None, description="ngrok reserved domain (tunnel profile)")

    # ── Feature switches ─────────────────────────────────────────────────
    OWNER_BOOTSTRAP: Optional[str] = Field(None, description="0 disables owner auto-creation")
    SETTINGS_SCHEMA_PATH: Optional[str] = Field(None, description="Override the schema file location")
    FORECAST_METHOD: Optional[str] = Field(None, description="auto | random_walk")


_settings: Optional[EnvSettings] = None


def get_env() -> EnvSettings:
    """Process-wide singleton."""
    global _settings
    if _settings is None:
        _settings = EnvSettings()
    return _settings


def documented_names() -> list[str]:
    """Every variable this model declares — the inventory the docs test uses."""
    return sorted(EnvSettings.model_fields.keys())
