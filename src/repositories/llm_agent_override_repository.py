"""
LLMAgentOverrideRepository — Data access layer for llm_agent_overrides.

Provides CRUD operations for per-agent model override records.

Design: docs/architecture/multi_provider_multi_model_design.md §3.4 / §8.4 C1
"""
from __future__ import annotations

import logging
import uuid
from typing import List, Optional

from src.data.database import get_db_connection
from src.data.models import LLMAgentOverride

logger = logging.getLogger(__name__)


class LLMAgentOverrideRepository:
    """
    Repository for llm_agent_overrides table.

    All methods open their own DB session via get_db_connection() unless
    an external session is injected (for unit-test isolation).
    """

    def __init__(self, db_session=None):
        self._external_session = db_session

    # ──────────────────────────────────────────────────────────────────
    # Internal helpers
    # ──────────────────────────────────────────────────────────────────

    def _session(self):
        """Return the injected session or open a new one."""
        if self._external_session is not None:
            return self._external_session
        return get_db_connection()

    # ──────────────────────────────────────────────────────────────────
    # Read
    # ──────────────────────────────────────────────────────────────────

    def list_by_user(self, user_id: str) -> List[LLMAgentOverride]:
        """Return all agent overrides for a given user, ordered by agent_name."""
        session = self._session()
        try:
            rows = (
                session.query(LLMAgentOverride)
                .filter(LLMAgentOverride.user_id == user_id)
                .order_by(LLMAgentOverride.agent_name)
                .all()
            )
            return rows
        finally:
            if self._external_session is None:
                session.close()

    def get_by_agent(self, user_id: str, agent_name: str) -> Optional[LLMAgentOverride]:
        """Return the override for a specific agent, or None if not found."""
        session = self._session()
        try:
            return (
                session.query(LLMAgentOverride)
                .filter(
                    LLMAgentOverride.user_id == user_id,
                    LLMAgentOverride.agent_name == agent_name,
                )
                .first()
            )
        finally:
            if self._external_session is None:
                session.close()

    def get_by_id(self, override_id: str) -> Optional[LLMAgentOverride]:
        """Return an override by its primary key."""
        session = self._session()
        try:
            return (
                session.query(LLMAgentOverride)
                .filter(LLMAgentOverride.id == override_id)
                .first()
            )
        finally:
            if self._external_session is None:
                session.close()

    # ──────────────────────────────────────────────────────────────────
    # Write
    # ──────────────────────────────────────────────────────────────────

    def upsert(
        self,
        user_id: str,
        agent_name: str,
        override_tier: Optional[str],
        primary_model_id: Optional[str],
        fallback_model_ids: Optional[List[str]],
        forbid_local: bool,
        forbid_fallback: bool,
        enabled: bool,
        notes: Optional[str] = None,
    ) -> LLMAgentOverride:
        """
        Insert or update an agent override.

        Uses UNIQUE(user_id, agent_name) to decide insert vs update.
        Returns the persisted row.
        """
        session = self._session()
        try:
            existing = (
                session.query(LLMAgentOverride)
                .filter(
                    LLMAgentOverride.user_id == user_id,
                    LLMAgentOverride.agent_name == agent_name,
                )
                .first()
            )

            if existing:
                existing.override_tier = override_tier
                existing.primary_model_id = primary_model_id
                existing.fallback_model_ids = fallback_model_ids or []
                existing.forbid_local = forbid_local
                existing.forbid_fallback = forbid_fallback
                existing.enabled = enabled
                existing.notes = notes
                session.commit()
                session.refresh(existing)
                return existing
            else:
                row = LLMAgentOverride(
                    id=str(uuid.uuid4()),
                    user_id=user_id,
                    agent_name=agent_name,
                    override_tier=override_tier,
                    primary_model_id=primary_model_id,
                    fallback_model_ids=fallback_model_ids or [],
                    forbid_local=forbid_local,
                    forbid_fallback=forbid_fallback,
                    enabled=enabled,
                    notes=notes,
                )
                session.add(row)
                session.commit()
                session.refresh(row)
                return row
        except Exception as e:
            logger.warning(f'Exception in llm_agent_override_repository.py: {e}', exc_info=True)
            session.rollback()
            raise
        finally:
            if self._external_session is None:
                session.close()

    def delete(self, user_id: str, agent_name: str) -> bool:
        """
        Delete an agent override by (user_id, agent_name).

        Returns True if a row was deleted, False if not found.
        """
        session = self._session()
        try:
            row = (
                session.query(LLMAgentOverride)
                .filter(
                    LLMAgentOverride.user_id == user_id,
                    LLMAgentOverride.agent_name == agent_name,
                )
                .first()
            )
            if row is None:
                return False
            session.delete(row)
            session.commit()
            return True
        except Exception as e:
            logger.warning(f'Exception in llm_agent_override_repository.py: {e}', exc_info=True)
            session.rollback()
            raise
        finally:
            if self._external_session is None:
                session.close()

    def delete_all_for_user(self, user_id: str) -> int:
        """Delete all overrides for a user. Returns count deleted."""
        session = self._session()
        try:
            count = (
                session.query(LLMAgentOverride)
                .filter(LLMAgentOverride.user_id == user_id)
                .delete(synchronize_session=False)
            )
            session.commit()
            return count
        except Exception as e:
            logger.warning(f'Exception in llm_agent_override_repository.py: {e}', exc_info=True)
            session.rollback()
            raise
        finally:
            if self._external_session is None:
                session.close()

    def get_overrides_referencing_model(self, model_id: str) -> List[LLMAgentOverride]:
        """
        Return all overrides that reference a given model_id
        (either as primary_model_id or within fallback_model_ids).

        Used by ModelService.delete() to check for 409 conflicts.
        Note: fallback_model_ids is a JSON array; we do a string-contains
        check which is sufficient for UUID values.
        """
        session = self._session()
        try:
            rows = (
                session.query(LLMAgentOverride)
                .filter(LLMAgentOverride.primary_model_id == model_id)
                .all()
            )
            # Also check fallback_model_ids (JSON array) — string search
            all_rows = (
                session.query(LLMAgentOverride)
                .all()
            )
            fallback_refs = [
                r for r in all_rows
                if r.fallback_model_ids and model_id in (r.fallback_model_ids or [])
            ]
            # Merge, deduplicate by id
            seen = {r.id for r in rows}
            for r in fallback_refs:
                if r.id not in seen:
                    rows.append(r)
                    seen.add(r.id)
            return rows
        finally:
            if self._external_session is None:
                session.close()
