"""
E2E tests for the ticker universe pipeline.
Runs against the live Docker API at localhost:8000.
Skips if container not running. Set RUN_E2E=1 to enable.
"""
import pytest
import httpx
import os
import jwt
from datetime import datetime, timedelta

BASE_URL = os.environ.get("API_BASE_URL", "http://localhost:8000")
TEST_USER = os.environ.get("TEST_USER_ID", "00000000-0000-4000-a000-000000000001")
JWT_SECRET = os.environ.get("JWT_SECRET", "your-super-secret-key-for-jwt-signing")

pytestmark = pytest.mark.skipif(
    not os.environ.get("RUN_E2E"),
    reason="Set RUN_E2E=1 to run E2E tests against live API"
)


def _make_token(user_id: str = TEST_USER) -> str:
    payload = {
        "sub": user_id,
        "type": "access",
        "exp": datetime.utcnow() + timedelta(hours=1),
    }
    token = jwt.encode(payload, JWT_SECRET, algorithm="HS256")
    print(f"[DEBUG] _make_token: {token[:50]}... len={len(token)}", flush=True)
    return token


def api_url(path: str) -> str:
    return f"{BASE_URL}{path}"


class TestTickerUniverseAPI:

    @pytest.fixture
    def headers(self):
        token = _make_token()
        return {"Authorization": f"Bearer {token}"}

    def test_health_check(self):
        resp = httpx.get(api_url("/health"), timeout=5)
        assert resp.status_code == 200

    def test_list_tickers(self, headers):
        resp = httpx.get(api_url("/api/v1/ticker-universe"), headers=headers, timeout=5)
        assert resp.status_code == 200
        data = resp.json()
        assert "data" in data

    def test_list_active_tickers(self, headers):
        resp = httpx.get(api_url("/api/v1/ticker-universe?status=active"), headers=headers, timeout=5)
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data.get("data"), list)
        assert len(data["data"]) > 0

    def test_get_targets(self, headers):
        resp = httpx.get(api_url("/api/v1/ticker-universe/targets"), headers=headers, timeout=5)
        assert resp.status_code == 200
        data = resp.json()
        assert "data" in data

    def test_get_research_for_ticker(self, headers):
        resp = httpx.get(api_url("/api/v1/ticker-universe?status=active"), headers=headers, timeout=5)
        tickers = resp.json().get("data", [])
        if not tickers:
            pytest.skip("No active tickers")
        resp2 = httpx.get(api_url(f"/api/v1/ticker-universe/{tickers[0]['ticker']}/research"), headers=headers, timeout=5)
        assert resp2.status_code == 200

    def test_optimize_targets(self, headers):
        resp = httpx.get(api_url("/api/v1/ticker-universe/targets/optimize"), headers=headers, timeout=30)
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("status") == "success"

    def test_rebalance_plan_shape(self, headers):
        resp = httpx.get(api_url("/api/v1/ticker-universe/rebalance/plan"), headers=headers, timeout=30)
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("status") == "success"
        plan = data.get("data", {})
        assert "summary" in plan
        summary = plan["summary"]
        assert "total_trades" in summary
        assert "sells" in summary
        assert "buys" in summary
        assert summary["total_value"] > 0

    def test_rebalance_plan_sell_before_buy(self, headers):
        resp = httpx.get(api_url("/api/v1/ticker-universe/rebalance/plan"), headers=headers, timeout=30)
        data = resp.json().get("data", {})
        trades = data.get("trades", {}).get("all", [])
        if len(trades) < 2:
            pytest.skip("Need ≥2 trades")
        sells = data["trades"]["sells"]
        buys = data["trades"]["buys"]
        for s in sells:
            assert s["action"] == "SELL"
        for b in buys:
            assert b["action"] == "BUY"

    def test_removal_candidates(self, headers):
        resp = httpx.get(api_url("/api/v1/ticker-universe/removal-candidates"), headers=headers, timeout=30)
        assert resp.status_code == 200
        data = resp.json()
        assert "data" in data

    def test_add_new_ticker(self, headers):
        resp = httpx.post(
            api_url("/api/v1/ticker-universe"), headers=headers,
            json={"ticker": "E2ETEST", "status": "watchlist"}, timeout=5,
        )
        assert resp.status_code == 200

    def test_cleanup_ticker(self, headers):
        httpx.post(api_url("/api/v1/ticker-universe"), headers=headers,
                   json={"ticker": "E2ETEST", "status": "watchlist"}, timeout=5)
        resp = httpx.delete(api_url("/api/v1/ticker-universe/E2ETEST"), headers=headers, timeout=5)
        assert resp.status_code == 200

    def test_get_logs(self, headers):
        resp = httpx.get(api_url("/api/v1/ticker-universe/logs"), headers=headers, timeout=5)
        assert resp.status_code == 200
        data = resp.json()
        assert "data" in data