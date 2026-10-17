"""Beat-scheduled tasks must work with NO user_id and NO PRIMARY_USER_ID env var (the production stack sets neither).

Four tasks added for the mission watchdog / benchmark parking / Finnhub poll / strategy lab resolved the user only from
those env vars, so every scheduled run returned "Error: user_id is required" and never executed (the daily watchdog
had never succeeded; Monday's SPY parking would have silently never run).
"""
import ast
import re
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

ROOT = Path(__file__).resolve().parents[3]
TASKS = ROOT / "src/infrastructure/tasks.py"
BEAT = ROOT / "src/infrastructure/celery_app.py"
OWNER = "owner-test-id"


def _beat_task_names():
    return set(re.findall(r'"task":\s*"src\.infrastructure\.tasks\.([a-z_0-9]+)"', BEAT.read_text(encoding="utf-8")))


def test_no_directly_scheduled_task_depends_on_the_primary_user_env_var():
    src = TASKS.read_text(encoding="utf-8")
    fns = {n.name: n for n in ast.walk(ast.parse(src)) if isinstance(n, ast.FunctionDef)}
    offenders = [n for n in sorted(_beat_task_names())
                 if n in fns and not n.startswith("dispatch_")
                 and 'os.getenv("PRIMARY_USER_ID")' in (ast.get_source_segment(src, fns[n]) or "")]
    assert not offenders, (f"beat-scheduled tasks resolve the user only from PRIMARY_USER_ID/USER_ID (unset in prod): "
                           f"{offenders}. Use src.config.owner.resolve_user_id(user_id).")


@pytest.fixture(autouse=True)
def _no_env(monkeypatch):
    monkeypatch.delenv("PRIMARY_USER_ID", raising=False)
    monkeypatch.delenv("USER_ID", raising=False)


def test_mission_watchdog_runs_without_user_id_or_env():
    from src.infrastructure import tasks
    svc = MagicMock()
    svc.return_value.evaluate.return_value = {"overall": "OK", "breaches": [], "criteria": []}
    with patch("src.config.owner.resolve_user_id", return_value=OWNER), \
         patch("src.services.mission_watchdog_service.MissionWatchdogService", svc):
        res = tasks.run_mission_watchdog()
    assert isinstance(res, dict) and res["overall"] == "OK"
    assert svc.call_args.kwargs["user_id"] == OWNER


def test_benchmark_parking_runs_without_user_id_or_env():
    from src.infrastructure import tasks
    svc = MagicMock()
    svc.return_value.run = MagicMock(return_value={"action": "BUY", "amount_usd": 100.0, "executed": False, "reason": "x"})
    with patch("src.config.owner.resolve_user_id", return_value=OWNER), \
         patch.object(tasks, "is_market_open_today", return_value=True), \
         patch.object(tasks, "_run_async_safe", side_effect=lambda c: c), \
         patch("src.services.benchmark_parking_service.BenchmarkParkingService", svc):
        res = tasks.run_benchmark_parking()
    assert isinstance(res, dict) and res.get("action") == "BUY"
    assert svc.call_args.kwargs["user_id"] == OWNER


def test_finnhub_poll_runs_without_user_id_or_env():
    from src.infrastructure import tasks
    svc = MagicMock()
    svc.return_value.run = MagicMock(return_value={"status": "disabled"})
    with patch("src.config.owner.resolve_user_id", return_value=OWNER), \
         patch.object(tasks, "_run_async_safe", side_effect=lambda c: c), \
         patch("src.services.finnhub_poll_service.FinnhubPollService", svc):
        res = tasks.run_finnhub_poll()
    assert res == {"status": "disabled"}
    assert svc.call_args.args[0] == OWNER


def test_strategy_lab_loads_prices_as_the_owner():
    from src.infrastructure import tasks
    mds = MagicMock()
    lab = MagicMock()
    lab.return_value.run.return_value = {"n_trials_total": 1, "variants_evaluated": 1, "shadow_candidates": [],
                                         "trials_deferred": 0, "cap_reached": False}
    with patch("src.config.owner.resolve_user_id", return_value=OWNER), \
         patch("src.services.market_data_service.MarketDataService", mds), \
         patch("src.evaluation.data.load_price_panel", return_value=MagicMock()), \
         patch("src.services.strategy_lab_service.StrategyLabService", lab):
        res = tasks.run_strategy_lab()
    assert isinstance(res, dict)
    assert mds.call_args.kwargs["user_id"] == OWNER
