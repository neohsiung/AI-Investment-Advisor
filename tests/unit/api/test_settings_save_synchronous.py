"""
Contract tests for the settings save endpoint.
測試設定儲存端點的同步寫入契約。

Context (2026-08-02): POST /api/v1/settings used BackgroundTasks, so it
returned 200 before the write happened and discarded save_settings_bulk's
failure result. These are the most safety-critical writes in the system
(broker credentials, etoro_mode, the ai_trading_enabled kill switch) and the
frontend re-reads immediately after posting, so a fire-and-forget write both
raced the read and hid failures. Now synchronous: 200 means it landed, and a
repository failure surfaces as 500.
"""
import pytest
from unittest.mock import MagicMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

# Import the aggregating router FIRST. src.api.v1.router imports the endpoint
# modules, and the endpoint module imports get_current_user_id back from it —
# importing the endpoint directly hits that cycle mid-initialization.
# 先載入彙整用的 router，否則會撞到既有的循環匯入。
import src.api.v1.router  # noqa: F401
from src.api.v1.endpoints import settings as settings_endpoint
from src.api.v1.endpoints.settings import router, get_settings_service


def _client(service: MagicMock) -> TestClient:
    app = FastAPI()
    app.include_router(router, prefix="/settings")
    app.dependency_overrides[get_settings_service] = lambda: service
    return TestClient(app)


@pytest.fixture
def service():
    svc = MagicMock()
    svc.user_id = "test-user"
    svc.save_settings_bulk.return_value = (True, "Settings saved successfully.")
    return svc


class TestSaveSettingsIsSynchronous:

    def test_write_happens_before_response(self, service):
        """The repository must have been called by the time 200 comes back."""
        response = _client(service).post("/settings", json={"settings": {"etoro_mode": "demo"}})

        assert response.status_code == 200
        service.save_settings_bulk.assert_called_once_with({"etoro_mode": "demo"})

    def test_endpoint_declares_no_background_tasks(self):
        """Regression guard: reintroducing BackgroundTasks re-opens the race."""
        import inspect
        sig = inspect.signature(settings_endpoint.save_settings)

        assert "background_tasks" not in sig.parameters

    def test_repository_failure_surfaces_as_500(self, service):
        service.save_settings_bulk.return_value = (False, "Error saving settings: db down")

        response = _client(service).post("/settings", json={"settings": {"etoro_mode": "demo"}})

        assert response.status_code == 500
        assert "db down" in response.json()["detail"]

    def test_exception_surfaces_as_500(self, service):
        service.save_settings_bulk.side_effect = RuntimeError("boom")

        response = _client(service).post("/settings", json={"settings": {"etoro_mode": "demo"}})

        assert response.status_code == 500

    def test_success_response_shape(self, service):
        response = _client(service).post("/settings", json={"settings": {"a": "b"}})

        body = response.json()
        assert body["status"] == "success"
        assert body["message"]


class TestKillSwitchWriteShape:
    """
    The UI must send ai_trading_enabled as a STRING. settings.value is a JSON
    column; a raw boolean previously crashed RiskManager with AttributeError.
    """

    @pytest.mark.parametrize("value", ["true", "false"])
    def test_string_kill_switch_passes_through_unchanged(self, service, value):
        _client(service).post("/settings", json={"settings": {"ai_trading_enabled": value}})

        sent = service.save_settings_bulk.call_args[0][0]
        assert sent["ai_trading_enabled"] == value
        assert isinstance(sent["ai_trading_enabled"], str)
