"""
Single-owner identity resolver — the seam that collapses this codebase's
multi-tenant `user_id` plumbing onto one operator without touching the schema.

單機自架版的擁有者解析層。資料庫保留 `user_id` 欄位與所有索引/主鍵，
只是全系統實際上只有一位擁有者；所有「沒有帶 user_id」的呼叫端都在這裡
被解析成同一個 OWNER_ID。

Design rules that matter:

1. **This module must not import any project module at import time.**
   `settings_repository` imports it, and nearly everything imports
   `settings_repository`. A top-level project import here would deadlock the
   whole package graph. Every DB import lives inside a function body.
   本模組頂層不得 import 任何專案模組（會炸循環相依）。

2. `resolve_user_id()` is a *resolver*, not a rewriter. Only the "no identity
   supplied" sentinels map to the owner; an explicit foreign UUID is passed
   through untouched, so the existing isolation code paths (and their tests)
   keep their meaning and a future multi-user mode stays reachable.

3. The `lru_cache` never caches a negative result — a lookup that ran before
   the database was seeded must not pin `None` for the process lifetime.
"""
from __future__ import annotations

import logging
import os
import threading
from functools import lru_cache
from typing import List, Optional

logger = logging.getLogger(__name__)

# Sentinels meaning "the caller did not supply an identity". Historically the
# codebase used a mix of these; `'system'` was the pre-v4.3 global user.
_UNSET_SENTINELS = frozenset({None, "", "none", "null", "system", "default"})

# Deterministic id used when bootstrapping a brand-new install. Matches
# scripts/seed_user.py so an existing seeded database resolves to the same row.
DEFAULT_OWNER_ID = "00000000-0000-4000-a000-000000000001"
DEFAULT_OWNER_EMAIL = "owner@localhost"

# Postgres advisory-lock key for the bootstrap critical section. Arbitrary but
# fixed: every process must pick the same number for the lock to serialise.
_BOOTSTRAP_LOCK_KEY = 8_615_231_907

_bootstrap_lock = threading.Lock()


class OwnerNotResolved(RuntimeError):
    """Raised when no owner exists and bootstrapping is disabled or failed."""


def _is_unset(user_id: Optional[str]) -> bool:
    """True when `user_id` carries no real identity."""
    if user_id is None:
        return True
    if not isinstance(user_id, str):
        return False
    return user_id.strip().lower() in _UNSET_SENTINELS


def _env_owner_id() -> Optional[str]:
    """Owner id pinned by environment, if any. First non-empty wins."""
    for key in ("OWNER_ID", "PRIMARY_USER_ID", "USER_ID"):
        value = os.getenv(key, "").strip()
        if value and not _is_unset(value):
            return value
    return None


def _lookup_existing_owner() -> Optional[str]:
    """Oldest active user row, or None on an unseeded/unreachable database."""
    try:
        from src.repositories.user_repository import AlchemyUserRepository

        return AlchemyUserRepository().get_first_user_id()
    except Exception as exc:
        logger.warning("owner: could not read users table (%s)", exc)
        return None


def _bootstrap_owner() -> Optional[str]:
    """
    Create the owner row, serialised by a Postgres advisory lock.

    Five processes (api, workers, beat, webhook handlers) can race here on a
    fresh install; without the lock they each insert a row and
    `get_first_user_id()` stops being deterministic, which silently splits
    settings across two ids.
    """
    if os.getenv("OWNER_BOOTSTRAP", "1").strip().lower() in ("0", "false", "no"):
        return None

    import uuid

    from sqlalchemy import text

    from src.data.database import get_db_engine

    owner_id = os.getenv("OWNER_ID", "").strip() or DEFAULT_OWNER_ID
    email = os.getenv("OWNER_EMAIL", "").strip() or DEFAULT_OWNER_EMAIL
    name = os.getenv("OWNER_NAME", "").strip() or "Owner"

    engine = get_db_engine()
    with engine.begin() as conn:
        # Transaction-scoped advisory lock, released on commit/rollback. This
        # is what serialises the five processes that can race here on a fresh
        # install. Postgres-only: SQLite (tests, local tooling) has no such
        # function and would raise OperationalError, so fall back to the
        # in-process lock plus the re-read below — adequate there, since those
        # backends are single-process by construction.
        # advisory lock 僅 Postgres 提供；SQLite 退回行程內鎖 + 重讀。
        if conn.engine.dialect.name == "postgresql":
            conn.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": _BOOTSTRAP_LOCK_KEY})

        # Re-read inside the lock — another process may have just seeded.
        row = conn.execute(
            text(
                "SELECT id FROM users "
                "WHERE email NOT LIKE 'test%' "
                "AND email NOT LIKE '%@example.com' "
                "AND id != 'default' "
                "ORDER BY created_at ASC LIMIT 1"
            )
        ).fetchone()
        if row:
            return row[0]

        # NOW() is Postgres; SQLite needs CURRENT_TIMESTAMP.
        now_fn = "NOW()" if conn.engine.dialect.name == "postgresql" else "CURRENT_TIMESTAMP"
        conn.execute(
            text(
                "INSERT INTO users (id, email, name, created_at) "
                f"VALUES (:uid, :email, :name, {now_fn}) "
                "ON CONFLICT (id) DO NOTHING"
            ),
            {"uid": owner_id, "email": email, "name": name},
        )
        # `user_identities.id` has a Python-side default only, and `is_primary`
        # is an Integer (0/1), not a boolean — raw SQL must supply both.
        conn.execute(
            text(
                "INSERT INTO user_identities (id, user_id, provider, identifier, is_primary) "
                "SELECT :iid, :uid, 'email', :email, 1 "
                "WHERE NOT EXISTS ("
                "  SELECT 1 FROM user_identities WHERE provider = 'email' AND identifier = :email"
                ")"
            ),
            {"iid": str(uuid.uuid4()), "uid": owner_id, "email": email},
        )

    logger.info("owner: bootstrapped owner %s (%s)", owner_id, email)
    return owner_id


@lru_cache(maxsize=1)
def _cached_owner_id() -> str:
    """Cached resolution. Only ever reached with a successful result."""
    owner = _env_owner_id() or _lookup_existing_owner()
    if owner:
        return owner

    with _bootstrap_lock:
        owner = _lookup_existing_owner() or _bootstrap_owner()

    if not owner:
        raise OwnerNotResolved(
            "No owner user could be resolved. Set OWNER_ID in .env, or run "
            "`python -m src.config.owner --bootstrap` against a migrated database."
        )
    return owner


def get_owner_id() -> str:
    """
    The single operator's user id.

    Resolution order: OWNER_ID/PRIMARY_USER_ID/USER_ID env → oldest active
    `users` row → bootstrap a new row. Raises `OwnerNotResolved` if all three
    fail, because silently inventing an id here would scatter settings.
    """
    return _cached_owner_id()


def resolve_user_id(user_id: Optional[str] = None) -> str:
    """
    Map a possibly-absent user id onto a real one.

    An explicit, non-sentinel id is returned unchanged — this function narrows
    "no identity" to the owner, it does not force every caller onto the owner.
    明確傳入的其他 UUID 原樣放行，只有「未指定」才落到擁有者。
    """
    if _is_unset(user_id):
        return get_owner_id()
    return user_id


def active_user_ids() -> List[str]:
    """
    Every user the scheduler should fan out over — exactly one, by design.

    Replaces `AlchemyUserRepository.get_all_active_users()` at scheduling call
    sites so a stray extra `users` row can never double the LLM bill.
    """
    return [get_owner_id()]


def reset_owner_cache() -> None:
    """Drop the memoised owner. For tests and for post-bootstrap re-resolution."""
    _cached_owner_id.cache_clear()


def _main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Owner identity bootstrap")
    parser.add_argument(
        "--bootstrap",
        action="store_true",
        help="Ensure the owner row exists, then print its id. Run this once "
             "before any application process starts.",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    if not args.bootstrap:
        parser.print_help()
        return 2

    try:
        owner = get_owner_id()
    except OwnerNotResolved as exc:
        print(f"ERROR: {exc}")
        return 1
    print(owner)
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
