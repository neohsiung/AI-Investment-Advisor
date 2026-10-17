"""Mission API errors must not echo exception text to the client (CodeQL py/stack-trace-exposure, alert #164)."""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.v1.dependencies import get_current_user_id
from src.api.v1.endpoints.mission import router

app = FastAPI()
app.include_router(router, prefix="/api/v1/mission")
app.dependency_overrides[get_current_user_id] = lambda: "test-user"
client = TestClient(app)

SECRET_TEXT = "postgresql://user:hunter2@db/prod connection refused"


@pytest.mark.parametrize("path,target,attr", [
    ("/api/v1/mission/status", "src.services.mission_watchdog_service.MissionWatchdogService", "evaluate"),
    ("/api/v1/mission/parking-plan", "src.services.benchmark_parking_service.BenchmarkParkingService", "build_plan"),
    ("/api/v1/mission/strategies", "src.services.strategy_lab_service.StrategyLabService", "list_trials"),
])
def test_failures_return_a_generic_500_without_the_exception_text(path, target, attr):
    with patch(target) as svc_cls:
        inst = svc_cls.return_value
        setattr(inst, attr, AsyncMock(side_effect=RuntimeError(SECRET_TEXT)) if attr == "build_plan"
                else MagicMock(side_effect=RuntimeError(SECRET_TEXT)))
        resp = client.get(path)
    assert resp.status_code == 500
    body = resp.text
    assert "hunter2" not in body and "postgresql" not in body and "connection refused" not in body
