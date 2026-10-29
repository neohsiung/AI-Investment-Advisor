from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.v1.dependencies import get_current_user_id
from src.api.v1.endpoints.market import router

app = FastAPI()
app.include_router(router, prefix="/api/v1/market")
app.dependency_overrides[get_current_user_id] = lambda: "test-user"
client = TestClient(app)


def _get(session):
    with patch("src.api.v1.endpoints.market.MarketClock") as clock_cls:
        clock_cls.return_value.session_today.return_value = session
        return client.get("/api/v1/market/today")


def test_closed_day():
    assert _get(False).json()["data"]["state"] == "closed"


def test_trading_day():
    assert _get(True).json()["data"]["state"] == "trading_day"


def test_no_calendar_is_unknown_not_a_guess():
    assert _get(None).json()["data"]["state"] == "unknown"


def test_failure_is_a_500_without_the_cause():
    with patch("src.api.v1.endpoints.market.MarketClock", side_effect=RuntimeError("boom")):
        resp = client.get("/api/v1/market/today")
    assert resp.status_code == 500 and "boom" not in resp.json()["detail"]


def test_router_is_wired_under_v1():
    from src.api.v1.router import api_v1_router
    assert "/market/today" in {r.path for r in api_v1_router.routes}
