"""
LLMProviderRepository — DB access layer for `llm_providers` (Phase A).

Follows the project repository style (see settings_repository).
All operations use the SQLAlchemy ORM scoped session.

See docs/architecture/multi_provider_multi_model_design.md §3.1 / §8.2 A4.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import func

from src.data.database import BaseRepository, get_db_engine
from src.data.models import LLMProvider, LLMModel


logger = logging.getLogger(__name__)


class LLMProviderRepository(BaseRepository):
    """CRUD for `llm_providers` rows scoped to a user."""

    def __init__(self, engine: Any = None):
        BaseRepository.__init__(self, engine or get_db_engine())

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------
    def list_by_user(self, user_id: str) -> List[LLMProvider]:
        """Return all providers owned by `user_id` (enabled + disabled)."""
        session = self.session
        try:
            rows = (
                session.query(LLMProvider)
                .filter(LLMProvider.user_id == user_id)
                .order_by(LLMProvider.provider_code, LLMProvider.display_name)
                .all()
            )
            return rows
        finally:
            session.close()

    def get(self, provider_id: str) -> Optional[LLMProvider]:
        """Return a single provider by id (or None)."""
        session = self.session
        try:
            return session.query(LLMProvider).filter(LLMProvider.id == provider_id).one_or_none()
        finally:
            session.close()

    def get_for_user(self, provider_id: str, user_id: str) -> Optional[LLMProvider]:
        """Return a provider that matches both id and owning user."""
        session = self.session
        try:
            return (
                session.query(LLMProvider)
                .filter(LLMProvider.id == provider_id, LLMProvider.user_id == user_id)
                .one_or_none()
            )
        finally:
            session.close()

    def count_models(self, provider_id: str) -> int:
        """Return how many `llm_models` rows reference this provider."""
        session = self.session
        try:
            return int(
                session.query(func.count(LLMModel.id))
                .filter(LLMModel.provider_id == provider_id)
                .scalar() or 0
            )
        finally:
            session.close()

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------
    def create(self, user_id: str, payload: Dict[str, Any]) -> str:
        """
        Insert a new provider. Returns the new row id.

        Required `payload` keys: provider_code, display_name.
        Optional: base_url, encrypted_api_key, enabled, extra_config.
        """
        new_id = str(uuid.uuid4())
        row = LLMProvider(
            id=new_id,
            user_id=user_id,
            provider_code=payload["provider_code"],
            display_name=payload["display_name"],
            base_url=payload.get("base_url"),
            encrypted_api_key=payload.get("encrypted_api_key"),
            enabled=bool(payload.get("enabled", True)),
            extra_config=payload.get("extra_config") or {},
        )
        session = self.session
        try:
            session.add(row)
            session.commit()
            logger.info("LLMProviderRepository.create: %s user=%s code=%s",
                        new_id, user_id, payload["provider_code"])
            return new_id
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def update(self, provider_id: str, patch: Dict[str, Any]) -> Optional[LLMProvider]:
        """Apply partial update. Returns the updated row (or None if not found)."""
        session = self.session
        try:
            row = session.query(LLMProvider).filter(LLMProvider.id == provider_id).one_or_none()
            if row is None:
                return None
            allowed = {
                "display_name", "base_url", "encrypted_api_key",
                "enabled", "extra_config",
                "health_status", "health_detail", "last_checked_at",
            }
            for k, v in patch.items():
                if k in allowed:
                    setattr(row, k, v)
            row.updated_at = datetime.now(timezone.utc)
            session.commit()
            session.refresh(row)
            logger.info("LLMProviderRepository.update: %s", provider_id)
            return row
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def delete(self, provider_id: str) -> bool:
        """
        Delete the provider. Caller should pre-check `count_models` and
        raise a 409 at the service/API layer if > 0.
        Returns True if a row was deleted.
        """
        session = self.session
        try:
            row = session.query(LLMProvider).filter(LLMProvider.id == provider_id).one_or_none()
            if row is None:
                return False
            session.delete(row)
            session.commit()
            logger.info("LLMProviderRepository.delete: %s", provider_id)
            return True
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()
