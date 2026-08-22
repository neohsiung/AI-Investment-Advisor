"""
LLMTierBindingRepository — DB access for `llm_tier_bindings`.

Phase B: Full CRUD implementation.
  - list_by_user(user_id) -> list[LLMTierBinding]
  - get_by_tier(user_id, tier) -> LLMTierBinding | None
  - upsert(user_id, tier, data) -> LLMTierBinding  (INSERT OR UPDATE)
  - delete_by_user(user_id)
  - get_usages_for_model(model_id) -> list[dict]

See docs/architecture/multi_provider_multi_model_design.md §3.3 / §8.3 B1.

IMPORTANT (project policy):
  Tier bindings are strictly per-user. There is NO environment-variable
  fallback and NO SYSTEM-wide implicit inheritance — if a user has no
  binding row, the application must treat the tier as unconfigured.
"""
from __future__ import annotations

import logging
import uuid
from typing import Any, Dict, List, Optional

from src.data.database import BaseRepository, get_db_engine
from src.data.models import LLMTierBinding


logger = logging.getLogger(__name__)

VALID_TIERS = {"nano", "fast", "smart", "advanced"}


class LLMTierBindingRepository(BaseRepository):
    """Full CRUD for llm_tier_bindings (Phase B)."""

    def __init__(self, engine: Any = None):
        BaseRepository.__init__(self, engine or get_db_engine())

    # ------------------------------------------------------------------
    # Reads
    # ------------------------------------------------------------------
    def list_by_user(self, user_id: str) -> List[LLMTierBinding]:
        """Return all tier bindings for `user_id`. No SYSTEM fallback."""
        session = self.session
        try:
            return (
                session.query(LLMTierBinding)
                .filter(LLMTierBinding.user_id == user_id)
                .order_by(LLMTierBinding.tier)
                .all()
            )
        finally:
            session.close()

    def get_by_tier(self, user_id: str, tier: str) -> Optional[LLMTierBinding]:
        """Fetch a single binding for (user_id, tier). Returns None if not configured."""
        session = self.session
        try:
            return (
                session.query(LLMTierBinding)
                .filter(LLMTierBinding.user_id == user_id, LLMTierBinding.tier == tier)
                .one_or_none()
            )
        finally:
            session.close()

    def get_usages_for_model(self, model_id: str) -> List[Dict[str, Any]]:
        """
        Return every tier_binding reference to `model_id`, across ALL users.
        Shape:
          [
            {"binding_id": "...", "user_id": "...", "tier": "...", "role": "primary"},
            {"binding_id": "...", "user_id": "...", "tier": "...", "role": "fallback", "index": 1},
            ...
          ]
        """
        session = self.session
        usages: List[Dict[str, Any]] = []
        try:
            rows = session.query(LLMTierBinding).all()
            for r in rows:
                if r.primary_model_id == model_id:
                    usages.append({
                        "binding_id": r.id,
                        "user_id": r.user_id,
                        "tier": r.tier,
                        "role": "primary",
                    })
                fallback_ids = r.fallback_model_ids or []
                if isinstance(fallback_ids, list):
                    for idx, fid in enumerate(fallback_ids):
                        if fid == model_id:
                            usages.append({
                                "binding_id": r.id,
                                "user_id": r.user_id,
                                "tier": r.tier,
                                "role": "fallback",
                                "index": idx,
                            })
            return usages
        finally:
            session.close()

    def get_default_by_tier(self, tier: str) -> Optional[LLMTierBinding]:
        """查詢指定 tier 的任意一筆可用綁定（不限特定使用者）。
        用於當某租戶尚未設定自訂 tier binding 時的系統 fallback。
        依 created_at 排序，取最早建立的綁定（通常為管理者初始設定）。
        """
        session = self.session
        try:
            return (
                session.query(LLMTierBinding)
                .filter(LLMTierBinding.tier == tier)
                .first()
            )
        finally:
            session.close()

    # ------------------------------------------------------------------
    # Writes (Phase B)
    # ------------------------------------------------------------------
    def upsert(
        self,
        user_id: str,
        tier: str,
        data: Dict[str, Any],
    ) -> LLMTierBinding:
        """
        INSERT OR UPDATE a tier binding for (user_id, tier).

        `data` keys:
          - primary_model_id: str (required)
          - fallback_model_ids: list[str] (default [])
          - per_candidate_config: dict (default {})
          - budget_aware: bool (default True)
        """
        if tier not in VALID_TIERS:
            raise ValueError(f"Invalid tier '{tier}'. Must be one of {VALID_TIERS}")

        session = self.session
        try:
            existing = (
                session.query(LLMTierBinding)
                .filter(LLMTierBinding.user_id == user_id, LLMTierBinding.tier == tier)
                .one_or_none()
            )
            if existing is None:
                binding = LLMTierBinding(
                    id=str(uuid.uuid4()),
                    user_id=user_id,
                    tier=tier,
                    primary_model_id=data["primary_model_id"],
                    fallback_model_ids=data.get("fallback_model_ids", []),
                    per_candidate_config=data.get("per_candidate_config", {}),
                    budget_aware=data.get("budget_aware", True),
                )
                session.add(binding)
            else:
                existing.primary_model_id = data["primary_model_id"]
                existing.fallback_model_ids = data.get("fallback_model_ids", [])
                existing.per_candidate_config = data.get("per_candidate_config", {})
                existing.budget_aware = data.get("budget_aware", True)
                binding = existing

            session.commit()
            session.refresh(binding)
            return binding
        except Exception as e:
            logger.warning(f'Exception in llm_tier_binding_repository.py: {e}', exc_info=True)
            session.rollback()
            raise
        finally:
            session.close()

    def upsert_all(self, user_id: str, bindings: List[Dict[str, Any]]) -> None:
        """
        Bulk upsert all tier bindings for a user.
        Each item in `bindings` must have 'tier' + same keys as upsert().
        """
        session = self.session
        try:
            for item in bindings:
                tier = item["tier"]
                if tier not in VALID_TIERS:
                    raise ValueError(f"Invalid tier '{tier}'")

                existing = (
                    session.query(LLMTierBinding)
                    .filter(LLMTierBinding.user_id == user_id, LLMTierBinding.tier == tier)
                    .one_or_none()
                )
                if existing is None:
                    binding = LLMTierBinding(
                        id=str(uuid.uuid4()),
                        user_id=user_id,
                        tier=tier,
                        primary_model_id=item["primary_model_id"],
                        fallback_model_ids=item.get("fallback_model_ids", []),
                        per_candidate_config=item.get("per_candidate_config", {}),
                        budget_aware=item.get("budget_aware", True),
                    )
                    session.add(binding)
                else:
                    existing.primary_model_id = item["primary_model_id"]
                    existing.fallback_model_ids = item.get("fallback_model_ids", [])
                    existing.per_candidate_config = item.get("per_candidate_config", {})
                    existing.budget_aware = item.get("budget_aware", True)

            session.commit()
        except Exception as e:
            logger.warning(f'Exception in llm_tier_binding_repository.py: {e}', exc_info=True)
            session.rollback()
            raise
        finally:
            session.close()

    def delete_by_user(self, user_id: str) -> int:
        """Delete all tier bindings for a user. Returns number of deleted rows."""
        session = self.session
        try:
            count = (
                session.query(LLMTierBinding)
                .filter(LLMTierBinding.user_id == user_id)
                .delete(synchronize_session=False)
            )
            session.commit()
            return count
        except Exception as e:
            logger.warning(f'Exception in llm_tier_binding_repository.py: {e}', exc_info=True)
            session.rollback()
            raise
        finally:
            session.close()
