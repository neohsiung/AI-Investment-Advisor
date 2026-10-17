"""WP3: due filter in SQL, proposal rows skip the LLM lesson, readers exclude counterfactuals."""
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from sqlalchemy import create_engine, text

from src.services.outcome_reflection_service import OutcomeReflectionService
from src.services.kelly_sizing_service import KellySizingService


def _svc(engine=None):
    with patch("src.services.outcome_reflection_service.get_db_engine", return_value=engine or MagicMock()), \
         patch("src.services.outcome_reflection_service.resolve_user_id", return_value="u"):
        return OutcomeReflectionService(user_id="u")


def test_due_filter_is_in_sql_and_not_cutoff_based():
    svc = _svc()
    conn = MagicMock()
    svc.engine.connect.return_value.__enter__.return_value = conn
    conn.execute.return_value = []
    svc._fetch_due_pending(50)
    sql = str(conn.execute.call_args[0][0])
    params = conn.execute.call_args[0][1]
    assert "decided_at + horizon_days * INTERVAL '1 day' <= NOW()" in sql
    assert "cutoff" not in params and "cutoff" not in sql
    assert "proposal_id" in sql


def test_not_yet_due_63d_rows_do_not_block_due_rows():
    """Semantic check of the predicate on SQLite (PG INTERVAL spelled for SQLite)."""
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE decision_outcomes (id TEXT, user_id TEXT, decided_at TIMESTAMP,"
                          " horizon_days INTEGER, resolved_at TIMESTAMP)"))
        for i in range(60):  # sort first by decided_at but are not due (63d horizon)
            conn.execute(text("INSERT INTO decision_outcomes VALUES (:i,'u',datetime('now','-10 days'),63,NULL)"),
                         {"i": f"far{i}"})
        conn.execute(text("INSERT INTO decision_outcomes VALUES ('due','u',datetime('now','-9 days'),5,NULL)"))
    q = text("""SELECT id FROM decision_outcomes WHERE user_id=:user_id AND resolved_at IS NULL
        AND datetime(decided_at, '+' || horizon_days || ' days') <= datetime('now')
        ORDER BY decided_at ASC LIMIT :limit""")
    with engine.connect() as c:
        ids = [r[0] for r in c.execute(q, {"user_id": "u", "limit": 50})]
    assert ids == ["due"]


def _row(proposal_id):
    return {"id": "d1", "ticker": "AAPL", "signal": "BUY", "agent_name": "A", "proposal_id": proposal_id,
            "price_at_decision": 100.0, "decided_at": datetime(2026, 9, 25, tzinfo=timezone.utc),
            "horizon_days": 5}


def test_proposal_rows_use_fallback_lesson_and_no_llm():
    svc = _svc()
    svc.engine.begin.return_value.__enter__.return_value = MagicMock()
    with patch.object(svc, "_fetch_price", return_value=90.0), \
         patch.object(svc, "_fetch_benchmark_window", return_value=(700.0, 700.0)), \
         patch.object(svc, "_generate_lesson") as llm, \
         patch.object(svc, "_distill_failure") as distill, \
         patch("src.services.rule_lifecycle_service.RuleLifecycleService"):
        assert svc._resolve_one(_row("p1")) is True
    llm.assert_not_called()
    distill.assert_not_called()


def test_non_proposal_rows_still_use_llm_lesson():
    svc = _svc()
    svc.engine.begin.return_value.__enter__.return_value = MagicMock()
    with patch.object(svc, "_fetch_price", return_value=110.0), \
         patch.object(svc, "_fetch_benchmark_window", return_value=(700.0, 700.0)), \
         patch.object(svc, "_generate_lesson", return_value="l") as llm, \
         patch("src.services.rule_lifecycle_service.RuleLifecycleService"):
        svc._resolve_one(_row(None))
    llm.assert_called_once()


def test_rule_lifecycle_gate_excludes_counterfactuals():
    import inspect
    from src.services import rule_lifecycle_service as m
    assert "NOT is_counterfactual" in inspect.getsource(m.RuleLifecycleService._gate_one)


def test_blindspot_scan_excludes_counterfactuals():
    from src.services import cognitive_blindspot_service as m
    cls = next(v for k, v in vars(m).items() if isinstance(v, type) and hasattr(v, "scan_and_detect_blindspots"))
    engine = MagicMock()
    conn = engine.connect.return_value.__enter__.return_value
    conn.execute.return_value.fetchall.return_value = []
    cls(user_id="u", engine=engine).scan_and_detect_blindspots()
    assert "NOT is_counterfactual" in " ".join(str(conn.execute.call_args[0][0]).split())


def test_kelly_excludes_counterfactual_outcomes():
    class Repo:
        def get_outcomes(self, **kw):
            return [{"pnl": 1.0, "pnl_pct": 0.5, "is_counterfactual": True},
                    {"pnl": -1.0, "pnl_pct": -0.5, "is_counterfactual": False}]
    svc = KellySizingService(user_id="u", outcome_repo=Repo())
    with patch.object(KellySizingService, "calculate_from_trades", return_value="ok") as calc:
        svc.evaluate_from_decision_outcomes(ticker="AAPL")
    assert calc.call_args[0][0] == [{"pnl": -1.0, "pnl_pct": -0.5}]
