"""
Write-only ledger of proposed setting changes (alembic 028 `parameter_proposals`).
設定變更提案的帳本（只新增，不套用）。

Tuning loops record WHAT they would change here; they never write the setting. Applying a proposal is the job
of the UI settings path or the future parameter engine (see tests/invariants/test_registered_key_writers.py).
調參迴圈只在此登記「想改什麼」，不直接寫設定；套用屬於 UI 設定路徑或未來的參數引擎。
"""
from __future__ import annotations

import json
import uuid
from typing import Any, Dict, Optional

from sqlalchemy import text

from src.data.database import get_db_engine

_INSERT = text("""
    INSERT INTO parameter_proposals (id, user_id, source, proposed_values, evidence, status, idempotency_key)
    VALUES (:id, :user_id, :source, :proposed_values, :evidence, 'proposed', :idempotency_key)
    ON CONFLICT (user_id, source, idempotency_key) DO NOTHING
""")
_FIND = text("""
    SELECT id FROM parameter_proposals
    WHERE user_id = :user_id AND source = :source AND idempotency_key = :idempotency_key
""")


class ParameterProposalRepository:
    def __init__(self, engine: Any = None):
        if engine is None:
            engine = get_db_engine()
        self.engine = engine

    def create(self, payload: Dict[str, Any]) -> Optional[str]:
        """Insert a proposal (idempotent on user/source/idempotency_key); returns its id. Raises on DB failure.
        新增提案（以 user/source/idempotency_key 冪等），回傳 id；資料庫失敗時拋出例外。"""
        params = {
            "id": str(uuid.uuid4()),
            "user_id": payload["user_id"],
            "source": payload["source"],
            "proposed_values": json.dumps(payload["proposed_values"]),
            "evidence": json.dumps(payload.get("evidence") or {}),
            "idempotency_key": payload["idempotency_key"],
        }
        with self.engine.begin() as conn:
            conn.execute(_INSERT, params)
            row = conn.execute(_FIND, params).fetchone()
        return str(row[0]) if row else None
