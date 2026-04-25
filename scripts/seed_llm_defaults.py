#!/usr/bin/env python3
"""
seed_llm_defaults.py — Manually seed LLM defaults for a specific user.

Usage:
    SEED_USER_ID=<uuid> python scripts/seed_llm_defaults.py [--force]
"""
import argparse
import logging
import os
import sys
from pathlib import Path

# Ensure project root is on sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.services.llm_onboarding_service import LLMOnboardingService

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

def main() -> None:
    parser = argparse.ArgumentParser(description="Seed LLM default providers, models, and tier bindings for a specific user.")
    parser.add_argument("--force", action="store_true", help="Overwrite existing tier bindings")
    args = parser.parse_args()

    user_id = os.environ.get("SEED_USER_ID")
    if not user_id:
        logger.error("SEED_USER_ID environment variable is required.")
        sys.exit(1)

    logger.info("Seeding LLM defaults for user_id=%s (force=%s)", user_id, args.force)
    service = LLMOnboardingService()
    service.seed_defaults_for_user(user_id=user_id, force=args.force)

if __name__ == "__main__":
    main()

