"""
Integration test for M-A0 (ADR-003): the rule lifecycle cycle on a real (sqlite) table must never
leave an evidence-free 'provisional' rule older than 14 days.
M-A0 整合測試：規則生命週期循環跑在真實（sqlite）表上，不得留下超過 14 天且無證據的 provisional 規則。
"""
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine, event, text
from sqlalchemy.pool import StaticPool

from src.services.rule_lifecycle_service import RuleLifecycleService


@pytest.fixture
def engine():
    eng = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})

    @event.listens_for(eng, "connect")
    def _register_now(dbapi_conn, _):
        # sqlite has no NOW(); the production SQL (Postgres) does.
        dbapi_conn.create_function("NOW", 0, lambda: datetime.now(timezone.utc).isoformat())

    with eng.begin() as conn:
        conn.execute(text("""
            CREATE TABLE agent_rules (
                id INTEGER PRIMARY KEY, user_id TEXT, agent_name TEXT, rule_text TEXT,
                source_decision_id TEXT, status TEXT, gate_status TEXT, gate_details TEXT,
                gate_checked_at TEXT, expires_at TEXT, updated_at TEXT, created_at TIMESTAMP
            )
        """))
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        for rid, age in ((1, 20), (2, 15), (3, 1)):
            conn.execute(
                text("""INSERT INTO agent_rules (id, user_id, agent_name, rule_text, status, created_at)
                        VALUES (:id, 'u1', 'Momentum', '- rule', 'candidate', :ts)"""),
                {"id": rid, "ts": now - timedelta(days=age)},
            )
    return eng


@pytest.mark.asyncio
async def test_lifecycle_cycle_end_to_end_no_promotion(engine):
    svc = RuleLifecycleService(user_id="u1")

    async def fake_gate(*_a, **_k):
        return "rejected", {"reason": "no edge"}

    with patch("src.data.database.get_db_engine", return_value=engine), \
         patch.object(svc, "_gate_one", side_effect=fake_gate), \
         patch.object(svc, "_refresh_file_cache"):
        stats = await svc.gate_candidate_rules()

    assert stats["expired"] == 2
    assert stats["provisional"] == 0
    with engine.connect() as conn:
        rows = conn.execute(text("SELECT id, status, gate_status FROM agent_rules ORDER BY id")).fetchall()
    by_id = {r[0]: (r[1], r[2]) for r in rows}
    assert by_id[1] == ("rejected", "expired_no_evidence")
    assert by_id[2] == ("rejected", "expired_no_evidence")
    assert by_id[3][0] != "candidate"  # young rule went through the evidence gate
    assert not any(gs == "provisional" for _, gs in by_id.values())
