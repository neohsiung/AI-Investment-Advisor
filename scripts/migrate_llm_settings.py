#!/usr/bin/env python3
"""
migrate_llm_settings.py — Migrate legacy AI_MODEL_* env vars to llm_tier_bindings.

For each user in the database:
  1. Read AI_MODEL_{NANO,FAST,SMART,ADVANCED} from their settings
  2. Infer provider_code from model string (see §7.2 of design doc)
  3. Find or create llm_providers row for that provider
  4. Find or create llm_models row for that model
  5. Create llm_tier_bindings row if not already present (idempotent)

Idempotent: safe to run multiple times. Already-migrated users are skipped.

Usage:
    python scripts/migrate_llm_settings.py [--dry-run] [--user-id USER_ID]

    --dry-run: show what would be done without writing to DB
    --user-id: migrate only a specific user (default: all users)

Design: docs/architecture/multi_provider_multi_model_design.md §7.3
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
import uuid
from pathlib import Path
from typing import Dict, List, Optional, Tuple

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# Tier → settings key mapping
TIER_ENV_KEYS = {
    "nano": "AI_MODEL_NANO",
    "fast": "AI_MODEL_FAST",
    "smart": "AI_MODEL_SMART",
    "advanced": "AI_MODEL_ADVANCED",
}

# Provider code → display name
PROVIDER_DISPLAY_NAMES = {
    "openrouter": "OpenRouter",
    "openai": "OpenAI",
    "gemini": "Google Gemini",
    "anthropic": "Anthropic",
    "ollama": "Ollama (Local)",
    "groq": "Groq",
}

# Provider code → default base URL
PROVIDER_DEFAULT_URLS = {
    "openrouter": "https://openrouter.ai/api/v1",
    "openai": "https://api.openai.com/v1",
    "gemini": "https://generativelanguage.googleapis.com/v1beta",
    "anthropic": "https://api.anthropic.com",
    "ollama": "http://localhost:11434/v1",
    "groq": "https://api.groq.com/openai/v1",
}


def infer_provider_code(model_name: str) -> str:
    """
    Infer provider_code from model name string.
    See design doc §7.2.
    """
    name = model_name.lower().strip()
    if any(name.startswith(p) for p in ["openai/", "anthropic/", "google/", "meta/", "mistral/"]):
        return "openrouter"
    if name.startswith("gemini-") or name.startswith("models/gemini"):
        return "gemini"
    if name.startswith("gpt-") or name.startswith("text-embedding-"):
        return "openai"
    if name.startswith("claude-"):
        return "anthropic"
    if ":" in name:
        return "ollama"
    return "openrouter"


def get_or_create_provider(
    session: object,
    user_id: str,
    provider_code: str,
    dry_run: bool = False,
) -> Optional[str]:
    """Find or create an llm_providers row. Returns provider_id."""
    from src.data.models import LLMProvider

    existing = (
        session.query(LLMProvider)  # type: ignore[attr-defined]
        .filter(
            LLMProvider.user_id == user_id,
            LLMProvider.provider_code == provider_code,
        )
        .first()
    )

    if existing:
        return existing.id

    provider_id = str(uuid.uuid4())
    display_name = PROVIDER_DISPLAY_NAMES.get(provider_code, provider_code)
    base_url = PROVIDER_DEFAULT_URLS.get(provider_code)

    logger.info(
        "    [%s] Creating provider '%s' (id=%s)",
        "DRY-RUN" if dry_run else "CREATE",
        provider_code,
        provider_id,
    )

    if not dry_run:
        provider = LLMProvider(
            id=provider_id,
            user_id=user_id,
            provider_code=provider_code,
            display_name=display_name,
            base_url=base_url,
            encrypted_api_key=None,
            enabled=True,
            extra_config={},
        )
        session.add(provider)  # type: ignore[attr-defined]
        session.flush()  # type: ignore[attr-defined]

    return provider_id


def get_or_create_model(
    session: object,
    provider_id: str,
    provider_code: str,
    model_code: str,
    dry_run: bool = False,
) -> Optional[str]:
    """Find or create an llm_models row. Returns model_id."""
    from src.data.models import LLMModel

    existing = (
        session.query(LLMModel)  # type: ignore[attr-defined]
        .filter(
            LLMModel.provider_id == provider_id,
            LLMModel.model_code == model_code,
        )
        .one_or_none()
    )

    if existing:
        return existing.id

    model_id = str(uuid.uuid4())
    logger.info(
        "    [%s] Creating model '%s/%s' (id=%s)",
        "DRY-RUN" if dry_run else "CREATE",
        provider_code,
        model_code,
        model_id,
    )

    if not dry_run:
        model = LLMModel(
            id=model_id,
            provider_id=provider_id,
            model_code=model_code,
            display_name=model_code,  # Use model_code as display name for migrated models
            capability_tool_calling=False,
            capability_vision=False,
            capability_json_mode=False,
            capability_streaming=True,
            capability_embeddings=False,
            source="seed",
            enabled=True,
        )
        session.add(model)  # type: ignore[attr-defined]
        session.flush()  # type: ignore[attr-defined]

    return model_id


def migrate_user(
    session: object,
    user_id: str,
    db_settings: Dict[str, str],
    dry_run: bool = False,
) -> int:
    """
    Migrate a single user's AI_MODEL_* settings to llm_tier_bindings.
    Returns number of tiers migrated.
    """
    from src.data.models import LLMTierBinding

    migrated = 0

    for tier, env_key in TIER_ENV_KEYS.items():
        # Check if already migrated
        existing_binding = (
            session.query(LLMTierBinding)  # type: ignore[attr-defined]
            .filter(
                LLMTierBinding.user_id == user_id,
                LLMTierBinding.tier == tier,
            )
            .one_or_none()
        )

        if existing_binding is not None:
            logger.debug("  Tier '%s' already migrated for user %s, skipping", tier, user_id)
            continue

        # Get model name from settings or environment
        model_name = db_settings.get(env_key) or os.getenv(env_key)
        if not model_name:
            logger.debug("  No model configured for tier '%s' (user=%s), skipping", tier, user_id)
            continue

        model_name = model_name.strip().strip('"').strip("'")
        provider_code = infer_provider_code(model_name)

        logger.info(
            "  Migrating tier '%s': model='%s' → provider='%s' (user=%s)",
            tier, model_name, provider_code, user_id,
        )

        # Get or create provider
        provider_id = get_or_create_provider(session, user_id, provider_code, dry_run)
        if provider_id is None:
            continue

        # Get or create model
        model_id = get_or_create_model(session, provider_id, provider_code, model_name, dry_run)
        if model_id is None:
            continue

        # Create tier binding
        logger.info(
            "    [%s] Creating tier binding '%s' → model_id=%s",
            "DRY-RUN" if dry_run else "CREATE",
            tier,
            model_id,
        )

        if not dry_run:
            binding = LLMTierBinding(
                id=str(uuid.uuid4()),
                user_id=user_id,
                tier=tier,
                primary_model_id=model_id,
                fallback_model_ids=[],
                per_candidate_config={},
                budget_aware=True,
            )
            session.add(binding)  # type: ignore[attr-defined]

        migrated += 1

    return migrated


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Migrate legacy AI_MODEL_* settings to llm_tier_bindings"
    )
    parser.add_argument("--dry-run", action="store_true", help="Show what would be done without writing")
    parser.add_argument("--user-id", help="Migrate only a specific user ID")
    args = parser.parse_args()

    from src.data.database import get_db_engine
    from src.data.models import User
    from sqlalchemy.orm import sessionmaker

    engine = get_db_engine()
    Session = sessionmaker(bind=engine)
    session = Session()

    try:
        # Get users to migrate
        if args.user_id:
            users = session.query(User).filter(User.id == args.user_id).all()
            if not users:
                logger.error("User '%s' not found", args.user_id)
                sys.exit(1)
        else:
            users = session.query(User).all()

        logger.info("=== Migrating %d user(s) ===", len(users))
        total_migrated = 0

        for user in users:
            logger.info("Processing user: %s (%s)", user.id, getattr(user, "email", "?"))

            # Get user's settings
            try:
                from src.services.settings_service import SettingsService
                settings_svc = SettingsService(user_id=user.id)
                db_settings = settings_svc.get_all_settings()
            except Exception as e:
                logger.warning("  Could not load settings for user %s: %s", user.id, e)
                db_settings = {}

            count = migrate_user(session, user.id, db_settings, dry_run=args.dry_run)
            total_migrated += count
            logger.info("  Migrated %d tier(s) for user %s", count, user.id)

        if not args.dry_run:
            session.commit()
            logger.info("=== Migration committed: %d tier bindings created ===", total_migrated)
        else:
            logger.info("=== DRY-RUN complete: would create %d tier bindings ===", total_migrated)

    except Exception as e:
        session.rollback()
        logger.error("Migration failed: %s", e)
        raise
    finally:
        session.close()


if __name__ == "__main__":
    main()
