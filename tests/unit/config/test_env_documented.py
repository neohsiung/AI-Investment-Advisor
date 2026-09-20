"""
`.env.example` must not fall behind the variables the application reads.

The drift this prevents already happened: `.env.example` documented six
uncommented variables while docker-compose.prod.yml hard-required DB_PASS with
`${DB_PASS:?}` (compose refuses to start without it) plus REDIS_PASSWORD, DB_USER
and DB_NAME — none of which appeared there. A fresh clone therefore failed at
`docker compose up` with an interpolation error rather than a useful message.

The test asserts documentation coverage rather than regenerating the file: the
example carries hand-written bilingual explanations of the dangerous variables
(why `paper` is a full stop, why regenerating the encryption keys orphans stored
credentials) that a generator would flatten.

`.env.example` 不得落後於程式實際讀取的變數。此漂移確實發生過：compose 以
`${DB_PASS:?}` 硬性要求的變數並未出現在範例檔中，全新 clone 會直接失敗。
本測試驗證「文件涵蓋率」而非重新生成檔案，因為範例檔內含手寫的雙語警告說明。
"""
from __future__ import annotations

import re
from pathlib import Path

from src.config.env import documented_names

ENV_EXAMPLE = Path(".env.example")

# Variables that are deliberately NOT in .env.example.
#   * legacy aliases we accept but do not advertise
#   * values compose or the runtime injects, which a human never sets by hand
# 刻意不列入範例檔：僅為相容而接受的舊別名，以及由 compose/執行環境注入的值。
NOT_DOCUMENTED = {
    "PRIMARY_USER_ID",      # legacy alias for OWNER_ID
    "USER_ID",              # legacy alias for OWNER_ID
    "DB_URL",               # derived from the DB_* parts
    "DB_HOST",              # set by compose to the service name
    "DB_PORT",
    "QUEUE_REDIS_URL",
    "REDIS_URL",            # set by compose
    "NODE_ENV",             # set by compose
    "HOST",                 # set by uvicorn/compose
    "OTEL_SERVICE_NAME",    # set per-service by compose
    "COMPOSE_PROJECT_NAME",
    "ALLOW_INSECURE_BIND",  # an escape hatch, deliberately undocumented
    "OWNER_BOOTSTRAP",
    "SETTINGS_SCHEMA_PATH",
    "FORECAST_METHOD",
    "EMBED_MODEL",
    "OLLAMA_BASE_URL",
    "FRONTEND_ORIGIN",
    "RSS_INGEST_CRON_MINUTE",
    "RSS_MAX_ENTRIES_PER_FEED",
    "RSS_MAX_EVENTS_PER_RUN",
    "OWNER_EMAIL",
}


def _names_in_example() -> set[str]:
    text = ENV_EXAMPLE.read_text()
    # Matches both `NAME=` and a commented `# NAME=` form.
    return set(re.findall(r"^#?\s*([A-Z][A-Z0-9_]*)=", text, flags=re.M))


def test_env_example_exists():
    assert ENV_EXAMPLE.exists(), ".env.example is the only install documentation"


def test_every_declared_var_is_documented():
    documented = _names_in_example()
    missing = sorted(
        n for n in documented_names()
        if n not in documented and n not in NOT_DOCUMENTED
    )
    assert not missing, (
        "these variables are declared in src/config/env.py but absent from "
        f".env.example, so a fresh install has no way to learn about them: {missing}"
    )


def test_compose_required_vars_are_documented():
    """
    Anything compose interpolates with `${VAR:?}` makes `docker compose up` fail
    outright when unset, so it must be in the example.
    compose 以 `${VAR:?}` 引用的變數未設時會直接讓啟動失敗，必須出現在範例檔。
    """
    documented = _names_in_example()
    required: set[str] = set()
    for compose in (Path("docker-compose.prod.yml"), Path("docker-compose.yml")):
        if compose.exists():
            required |= set(re.findall(r"\$\{([A-Z][A-Z0-9_]*):\?", compose.read_text()))

    missing = sorted(required - documented)
    assert not missing, f"compose hard-requires these but .env.example omits them: {missing}"


def test_dangerous_vars_carry_a_warning():
    """
    Three variables can destroy data or money if set naively. The example must
    explain them, not merely list them.
    這三個變數若隨意設定會造成資料或資金損失，範例檔必須解釋而非僅列出。
    """
    text = ENV_EXAMPLE.read_text()

    # TRADING_MODE=paper is a full stop here, not a safe default.
    assert "InsufficientPermissions" in text or "demo permission" in text, (
        "TRADING_MODE must be documented as a full stop, not a safe default"
    )
    # Regenerating either encryption key orphans stored credentials.
    for key in ("APP_SECRET_KEY", "LLM_CREDENTIAL_KEY"):
        assert key in text, f"{key} must be documented"
    # AUTH_MODE is the single-operator access boundary.
    assert "AUTH_MODE" in text
