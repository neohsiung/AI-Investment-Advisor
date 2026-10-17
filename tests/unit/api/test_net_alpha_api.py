from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.v1.dependencies import get_current_user_id
from src.api.v1.endpoints.net_alpha import router

app = FastAPI()
app.include_router(router, prefix="/api/v1/net-alpha")
app.dependency_overrides[get_current_user_id] = lambda: "test-user"
client = TestClient(app)


def test_net_alpha_returns_report_dict():
    report = MagicMock()
    report.to_dict.return_value = {"net_alpha_pct": 1.5, "return_method": "twr_snapshots"}
    with patch(
        "src.services.net_alpha_attribution_service.NetAlphaAttributionService"
    ) as svc_cls:
        svc_cls.return_value.calculate_complete_report = AsyncMock(return_value=report)
        resp = client.get("/api/v1/net-alpha?lookback_days=60")
    assert resp.status_code == 200
    assert resp.json()["data"]["return_method"] == "twr_snapshots"
    svc_cls.return_value.calculate_complete_report.assert_awaited_once_with(lookback_days=60)


def test_net_alpha_rejects_bad_lookback():
    assert client.get("/api/v1/net-alpha?lookback_days=1").status_code == 422


def test_net_alpha_surfaces_failure_as_500():
    with patch(
        "src.services.net_alpha_attribution_service.NetAlphaAttributionService"
    ) as svc_cls:
        svc_cls.return_value.calculate_complete_report = AsyncMock(side_effect=RuntimeError("boom"))
        resp = client.get("/api/v1/net-alpha")
    assert resp.status_code == 500
    assert "boom" not in resp.json()["detail"]      # CodeQL py/stack-trace-exposure: no exception text to the client
