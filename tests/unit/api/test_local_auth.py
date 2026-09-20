"""
Local single-operator access control.

Removing the login leaves the bind address as the only security boundary, and
this deployment can place real orders. These tests pin the three things that
make that acceptable:

  1. AUTH_MODE=none returns the owner without a token (loopback convenience).
  2. AUTH_MODE=token rejects anything but ADMIN_TOKEN, and fails CLOSED when
     ADMIN_TOKEN is empty — an empty expected value must never authenticate
     everyone.
  3. Binding to a non-loopback interface without a token refuses to start.

移除登入後，綁定位址就是唯一的安全邊界；本檔固定上述三項不變量。
"""
import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from src.api.middleware.local_auth import LocalAuthMiddleware, assert_safe_bind
from src.api.v1.router import get_current_user_id
from src.config.owner import reset_owner_cache

OWNER = "00000000-0000-4000-a000-000000000001"
TOKEN = "correct-horse-battery-staple"


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("OWNER_ID", OWNER)
    monkeypatch.delenv("AUTH_MODE", raising=False)
    monkeypatch.delenv("ADMIN_TOKEN", raising=False)
    monkeypatch.delenv("ALLOW_INSECURE_BIND", raising=False)
    reset_owner_cache()
    yield
    reset_owner_cache()


@pytest.fixture
def client():
    app = FastAPI()
    app.add_middleware(LocalAuthMiddleware)

    @app.get("/api/v1/whoami")
    def whoami(uid: str = Depends(get_current_user_id)):
        return {"uid": uid}

    @app.get("/health")
    def health():
        return {"ok": True}

    @app.post("/webhook/n8n")
    def webhook():
        return {"ok": True}

    return TestClient(app)


class TestOpenMode:

    def test_no_token_required_and_owner_is_returned(self, client):
        r = client.get("/api/v1/whoami")
        assert r.status_code == 200
        assert r.json() == {"uid": OWNER}


class TestTokenMode:

    @pytest.fixture(autouse=True)
    def _token_mode(self, monkeypatch):
        monkeypatch.setenv("AUTH_MODE", "token")
        monkeypatch.setenv("ADMIN_TOKEN", TOKEN)

    def test_missing_token_is_rejected(self, client):
        assert client.get("/api/v1/whoami").status_code == 401

    def test_wrong_token_is_rejected(self, client):
        assert client.get("/api/v1/whoami",
                          headers={"X-Admin-Token": "wrong"}).status_code == 401

    def test_admin_token_header_accepted(self, client):
        r = client.get("/api/v1/whoami", headers={"X-Admin-Token": TOKEN})
        assert r.status_code == 200 and r.json() == {"uid": OWNER}

    def test_bearer_accepted(self, client):
        r = client.get("/api/v1/whoami", headers={"Authorization": f"Bearer {TOKEN}"})
        assert r.status_code == 200 and r.json() == {"uid": OWNER}

    def test_empty_admin_token_fails_closed(self, client, monkeypatch):
        """
        The dangerous misconfiguration: an empty expected token compared with
        an empty presented token would otherwise let everybody through.
        空的 ADMIN_TOKEN 必須拒絕所有請求，不能變成全部放行。
        """
        monkeypatch.setenv("ADMIN_TOKEN", "")
        assert client.get("/api/v1/whoami").status_code == 500

    def test_health_stays_open_for_container_healthchecks(self, client):
        assert client.get("/health").status_code == 200

    def test_webhooks_keep_their_own_api_key_path(self, client):
        """Webhooks authenticate via X-API-Key in webhook_service, not this gate."""
        assert client.post("/webhook/n8n").status_code == 200


class TestBindSafety:

    @pytest.mark.parametrize("host", ["127.0.0.1", "localhost", "::1", "127.0.0.5"])
    def test_loopback_is_always_allowed(self, host):
        assert_safe_bind(host) is None

    @pytest.mark.parametrize("host", ["0.0.0.0", "192.168.1.10", "10.0.0.4"])
    def test_public_bind_without_a_token_refuses_to_start(self, host):
        with pytest.raises(RuntimeError, match="Refusing to start"):
            assert_safe_bind(host)

    def test_public_bind_with_token_mode_is_allowed(self, monkeypatch):
        monkeypatch.setenv("AUTH_MODE", "token")
        monkeypatch.setenv("ADMIN_TOKEN", TOKEN)
        assert_safe_bind("0.0.0.0") is None

    def test_token_mode_with_empty_token_still_refuses_public_bind(self, monkeypatch):
        monkeypatch.setenv("AUTH_MODE", "token")
        monkeypatch.setenv("ADMIN_TOKEN", "")
        with pytest.raises(RuntimeError):
            assert_safe_bind("0.0.0.0")

    def test_explicit_override_is_honoured_but_must_be_explicit(self, monkeypatch):
        monkeypatch.setenv("ALLOW_INSECURE_BIND", "1")
        assert_safe_bind("0.0.0.0") is None
