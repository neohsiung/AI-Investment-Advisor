"""Mission watchdog: kill criteria evaluated against real numbers, honest about what it cannot measure."""
from datetime import date
from unittest.mock import MagicMock

from src.services.mission_watchdog_service import MissionWatchdogService


def _svc(trades=None, nav=1700.0, llm30=0.0, sub=0.0, local_cash=1000.0, broker_cash=1000.0):
    s = MissionWatchdogService("u", engine=MagicMock(), nav_usd=nav, llm_cost_30d_usd=llm30,
                               monthly_subscription_usd=sub, local_cash_usd=local_cash, broker_cash_usd=broker_cash)
    s._trades = lambda since: trades or []
    s._trial_stats = lambda: (0, 0)
    return s


def _by_id(res):
    return {c["id"]: c for c in res["criteria"]}


def test_all_measurable_ok():
    res = _svc().evaluate(today=date(2026, 10, 16))
    c = _by_id(res)
    assert c["K1"]["status"] == "ok" and c["K2"]["status"] == "ok"
    assert c["K3"]["status"] == "ok" and c["K4"]["status"] == "ok"
    assert res["overall"] == "PARTIAL"            # K5-K7 are explicitly not measurable
    assert {c[k]["status"] for k in ("K5", "K6")} == {"not_measurable"}


def test_cost_ratio_breach():
    # $5 LLM in 30d -> ~$61/yr on $1700 NAV = 3.6% > 3%
    res = _svc(llm30=5.0).evaluate(today=date(2026, 10, 16))
    assert _by_id(res)["K1"]["status"] == "breach" and "K1" in res["breaches"] and res["overall"] == "BREACH"


def test_ledger_broker_mismatch_breach():
    res = _svc(local_cash=7605.0, broker_cash=1661.0).evaluate()
    assert _by_id(res)["K2"]["status"] == "breach"


def test_mass_sell_day_breaches_k3():
    d = date(2026, 9, 29)
    trades = [{"date": d, "ticker": f"T{i}", "action": "SELL", "amount": 60.0} for i in range(11)]
    res = _svc(trades=trades).evaluate(today=date(2026, 10, 16))
    k3 = _by_id(res)["K3"]
    assert k3["status"] == "breach" and "11 tickers" in k3["note"]


def test_turnover_breach():
    d = date(2026, 10, 10)
    trades = [{"date": d, "ticker": "A", "action": "BUY", "amount": 500.0}, {"date": d, "ticker": "A", "action": "SELL", "amount": 500.0}]
    res = _svc(trades=trades).evaluate(today=date(2026, 10, 16))
    assert _by_id(res)["K4"]["status"] == "breach"


def test_unmeasurable_inputs_are_reported_not_ok():
    s = _svc(nav=None)
    s._latest_snapshot = lambda: None
    res = s.evaluate()
    c = _by_id(res)
    assert c["K1"]["status"] == "not_measurable" and c["K3"]["status"] == "not_measurable"


def test_endpoint_returns_status(monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from unittest.mock import patch

    from src.api.v1.dependencies import get_current_user_id
    from src.api.v1.endpoints.mission import router

    app = FastAPI()
    app.include_router(router, prefix="/api/v1/mission")
    app.dependency_overrides[get_current_user_id] = lambda: "u"
    with patch("src.services.mission_watchdog_service.MissionWatchdogService.evaluate", return_value={"overall": "OK", "criteria": []}):
        r = TestClient(app).get("/api/v1/mission/status")
    assert r.status_code == 200 and r.json()["data"]["overall"] == "OK"


def test_k7_measurable_once_trials_exist():
    s = _svc()
    s._trial_stats = lambda: (9, 0)
    assert _by_id(s.evaluate())["K7"]["status"] == "ok"
    s._trial_stats = lambda: (9, 2)
    assert _by_id(s.evaluate())["K7"]["status"] == "breach"


def test_k3_k4_report_when_history_clears():
    from datetime import date, timedelta
    from src.services.mission_watchdog_service import MissionWatchdogService
    today = date(2026, 10, 16)
    svc = MissionWatchdogService("u", nav_usd=1000.0, llm_cost_30d_usd=0.0, monthly_subscription_usd=0.0,
                                 local_cash_usd=0.0, broker_cash_usd=0.0)
    svc._trades = lambda since: [{"date": today - timedelta(days=2), "ticker": f"T{i}", "action": "SELL", "amount": 200.0} for i in range(5)]
    svc._trial_stats = lambda: (0, 0)
    res = {r["id"]: r for r in svc.evaluate(today)["criteria"]}
    assert res["K3"]["status"] == "breach" and "clears 2026-11-" in res["K3"]["note"]
    assert res["K4"]["status"] == "breach" and "clears 2026-11-" in res["K4"]["note"]
