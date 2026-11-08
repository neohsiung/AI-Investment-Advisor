"""
Database password lookup — one place, no default.

Every code path that builds a Postgres URL from `DB_*` variables used to carry
its own lookup of the password with a literal string as the fallback value. A literal default is a
published credential: anyone who reads the repo knows the password the system
falls back to, and a misconfigured deploy silently connects with it instead of
failing. This function replaces all of them and raises when the value is
missing (AGENTS.md constraint #0: never fail silent on a decision path).
See docs/design/DD-2026-1026-leaked-secrets-rotation.md.

資料庫密碼的唯一讀取點，沒有預設值。寫死的預設密碼等於公開憑證，
設定漏掉時還會靜默用它連線；缺值時改成明確 raise。
"""
from __future__ import annotations

import os
from typing import Mapping, Optional

from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError


class MissingDbPasswordError(RuntimeError):
    """DB_PASS is not set; refusing to fall back to a default password."""


def require_db_password(env: Optional[Mapping[str, str]] = None) -> str:
    """
    Return the Postgres password from `DB_PASS` (or the legacy `DB_PASSWORD`).
    回傳 Postgres 密碼；缺值或空字串就 raise，不退回預設值。
    """
    source = os.environ if env is None else env
    for name in ("DB_PASS", "DB_PASSWORD"):
        value = source.get(name)
        if value:
            return value
    raise MissingDbPasswordError(
        "DB_PASS is not set. Set DB_PASS (in .env, a secret manager, or the CI env) "
        "or provide a full DB_URL; there is no default password. "
        "未設定 DB_PASS：請在 .env、金鑰庫或 CI 環境設定，或直接提供完整 DB_URL；系統不提供預設密碼。"
    )


def describe_db_target(url: str) -> str:
    """
    Return `host:port/dbname` for logging; the username and password are never included.
    回傳可寫進 log 的 `host:port/資料庫名`，不含帳號與密碼。
    """
    try:
        parsed = make_url(url)
    except ArgumentError:
        return "unparseable-url"
    host = parsed.host or "local"
    port = f":{parsed.port}" if parsed.port else ""
    return f"{host}{port}/{parsed.database or ''}"
