"""
LLMModelRepository — DB access for `llm_models` (Phase A).

Follows the project repository style. Tier/Override references to models
are always by FK — this repo does NOT embed or infer from env vars.

See docs/architecture/multi_provider_multi_model_design.md §3.2 / §8.2 A4.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import and_, or_

from src.data.database import BaseRepository, get_db_engine
from src.data.models import LLMModel, LLMProvider, LLMTierBinding


logger = logging.getLogger(__name__)


class LLMModelRepository(BaseRepository):
    """CRUD for `llm_models` rows."""

    def __init__(self, engine: Any = None):
        BaseRepository.__init__(self, engine or get_db_engine())

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------
    def list_by_user(
        self,
        user_id: str,
        enabled: Optional[bool] = None,
        capability: Optional[str] = None,
    ) -> List[LLMModel]:
        """
        Return all models whose owning Provider belongs to `user_id`.
        Optional filters:
          - `enabled`: True/False/None (no filter)
          - `capability`: one of {tool_calling, vision, json_mode, streaming, embeddings}
        """
        session = self.session
        try:
            q = (
                session.query(LLMModel)
                .join(LLMProvider, LLMModel.provider_id == LLMProvider.id)
                .filter(LLMProvider.user_id == user_id)
            )
            if enabled is not None:
                q = q.filter(LLMModel.enabled == enabled)
            if capability:
                col_name = f"capability_{capability}"
                col = getattr(LLMModel, col_name, None)
                if col is not None:
                    q = q.filter(col.is_(True))
            return q.order_by(LLMModel.model_code).all()
        finally:
            session.close()

    def list_by_provider(
        self,
        provider_id: str,
        enabled: Optional[bool] = None,
    ) -> List[LLMModel]:
        """List models belonging to a given provider."""
        session = self.session
        try:
            q = session.query(LLMModel).filter(LLMModel.provider_id == provider_id)
            if enabled is not None:
                q = q.filter(LLMModel.enabled == enabled)
            return q.order_by(LLMModel.model_code).all()
        finally:
            session.close()

    def get(self, model_id: str) -> Optional[LLMModel]:
        session = self.session
        try:
            return session.query(LLMModel).filter(LLMModel.id == model_id).one_or_none()
        finally:
            session.close()

    def get_by_provider_and_code(
        self, provider_id: str, model_code: str
    ) -> Optional[LLMModel]:
        """Unique lookup by (provider_id, model_code) — useful for upsert / dedup."""
        session = self.session
        try:
            return (
                session.query(LLMModel)
                .filter(
                    LLMModel.provider_id == provider_id,
                    LLMModel.model_code == model_code,
                )
                .one_or_none()
            )
        finally:
            session.close()

    def get_references(self, model_id: str) -> Dict[str, List[Dict[str, Any]]]:
        """
        Return which tier_bindings reference this model id
        (as primary or within fallback array).

        Phase A returns only `tier_bindings` — agent_overrides will be added
        in Phase C when that table exists.

        Return shape:
            {
              "tier_bindings": [
                {"tier": "nano", "role": "primary",   "user_id": "...", "binding_id": "..."},
                {"tier": "fast", "role": "fallback",  "user_id": "...", "binding_id": "...", "index": 1}
              ]
            }
        """
        session = self.session
        result: Dict[str, List[Dict[str, Any]]] = {"tier_bindings": []}
        try:
            bindings = session.query(LLMTierBinding).all()
            for b in bindings:
                if b.primary_model_id == model_id:
                    result["tier_bindings"].append({
                        "binding_id": b.id,
                        "tier": b.tier,
                        "role": "primary",
                        "user_id": b.user_id,
                    })
                fallback_ids = b.fallback_model_ids or []
                if isinstance(fallback_ids, list):
                    for idx, fid in enumerate(fallback_ids):
                        if fid == model_id:
                            result["tier_bindings"].append({
                                "binding_id": b.id,
                                "tier": b.tier,
                                "role": "fallback",
                                "user_id": b.user_id,
                                "index": idx,
                            })
            return result
        finally:
            session.close()

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------
    def create(self, payload: Dict[str, Any]) -> str:
        """
        Insert a new model. Required keys:
          provider_id, model_code, display_name.
        """
        new_id = str(uuid.uuid4())
        row = LLMModel(
            id=new_id,
            provider_id=payload["provider_id"],
            model_code=payload["model_code"],
            display_name=payload["display_name"],
            capability_tool_calling=bool(payload.get("capability_tool_calling", False)),
            capability_vision=bool(payload.get("capability_vision", False)),
            capability_json_mode=bool(payload.get("capability_json_mode", False)),
            capability_streaming=bool(payload.get("capability_streaming", True)),
            capability_embeddings=bool(payload.get("capability_embeddings", False)),
            context_window=payload.get("context_window"),
            input_cost_per_1k=payload.get("input_cost_per_1k"),
            output_cost_per_1k=payload.get("output_cost_per_1k"),
            source=payload.get("source", "manual"),
            raw_discovery=payload.get("raw_discovery"),
            enabled=bool(payload.get("enabled", True)),
            notes=payload.get("notes"),
        )
        session = self.session
        try:
            session.add(row)
            session.commit()
            logger.info("LLMModelRepository.create: %s provider=%s code=%s",
                        new_id, payload["provider_id"], payload["model_code"])
            return new_id
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def batch_create(self, items: List[Dict[str, Any]]) -> List[str]:
        """
        Bulk insert (e.g. from Discovery). Skips items whose
        (provider_id, model_code) already exists and returns only the
        newly-inserted row ids.
        """
        session = self.session
        new_ids: List[str] = []
        try:
            for payload in items:
                # dedup check
                existing = (
                    session.query(LLMModel.id)
                    .filter(
                        LLMModel.provider_id == payload["provider_id"],
                        LLMModel.model_code == payload["model_code"],
                    )
                    .first()
                )
                if existing:
                    logger.debug("batch_create: skip existing %s/%s",
                                 payload["provider_id"], payload["model_code"])
                    continue

                new_id = str(uuid.uuid4())
                row = LLMModel(
                    id=new_id,
                    provider_id=payload["provider_id"],
                    model_code=payload["model_code"],
                    display_name=payload["display_name"],
                    capability_tool_calling=bool(payload.get("capability_tool_calling", False)),
                    capability_vision=bool(payload.get("capability_vision", False)),
                    capability_json_mode=bool(payload.get("capability_json_mode", False)),
                    capability_streaming=bool(payload.get("capability_streaming", True)),
                    capability_embeddings=bool(payload.get("capability_embeddings", False)),
                    context_window=payload.get("context_window"),
                    input_cost_per_1k=payload.get("input_cost_per_1k"),
                    output_cost_per_1k=payload.get("output_cost_per_1k"),
                    source=payload.get("source", "auto_discovered"),
                    raw_discovery=payload.get("raw_discovery"),
                    enabled=bool(payload.get("enabled", True)),
                    notes=payload.get("notes"),
                )
                session.add(row)
                new_ids.append(new_id)
            session.commit()
            logger.info("LLMModelRepository.batch_create: inserted=%d", len(new_ids))
            return new_ids
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def update(self, model_id: str, patch: Dict[str, Any]) -> Optional[LLMModel]:
        """Partial update. `provider_id` and `model_code` are NOT mutable."""
        session = self.session
        try:
            row = session.query(LLMModel).filter(LLMModel.id == model_id).one_or_none()
            if row is None:
                return None
            allowed = {
                "display_name",
                "capability_tool_calling", "capability_vision", "capability_json_mode",
                "capability_streaming", "capability_embeddings",
                "context_window", "input_cost_per_1k", "output_cost_per_1k",
                "enabled", "notes",
            }
            for k, v in patch.items():
                if k in allowed:
                    setattr(row, k, v)
            row.updated_at = datetime.now(timezone.utc)
            session.commit()
            session.refresh(row)
            logger.info("LLMModelRepository.update: %s", model_id)
            return row
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def delete(self, model_id: str) -> bool:
        """
        Delete a model. Caller MUST verify `get_references(model_id)` is empty
        and raise a 409 at the service/API layer if not.
        """
        session = self.session
        try:
            row = session.query(LLMModel).filter(LLMModel.id == model_id).one_or_none()
            if row is None:
                return False
            session.delete(row)
            session.commit()
            logger.info("LLMModelRepository.delete: %s", model_id)
            return True
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()
