import pytest
from unittest.mock import patch, MagicMock
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.v1.endpoints.settings import router
from src.api.v1.dependencies import get_current_user_id

app = FastAPI()
app.include_router(router, prefix="/api/v1/settings")

app.dependency_overrides[get_current_user_id] = lambda: "test-user-123"
client = TestClient(app)


def test_get_cost_profiles():
    with patch("src.api.v1.endpoints.settings.CostProfileService") as MockService:
        mock_instance = MockService.return_value
        mock_instance.get_current_profile.return_value = {"id": "balanced"}
        mock_instance.list_profiles.return_value = [
            {"id": "frugal", "name": "Frugal"},
            {"id": "balanced", "name": "Balanced"},
            {"id": "aggressive", "name": "Aggressive"},
        ]

        resp = client.get("/api/v1/settings/cost-profiles")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "success"
        assert data["active_profile"] == "balanced"
        assert len(data["profiles"]) == 3


def test_apply_cost_profile_success():
    with patch("src.api.v1.endpoints.settings.CostProfileService") as MockService:
        mock_instance = MockService.return_value
        mock_instance.apply_profile.return_value = {"id": "frugal", "name": "Frugal (節省型)"}

        resp = client.post("/api/v1/settings/cost-profiles/apply", json={"profile": "frugal"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "success"
        assert "Frugal" in data["message"]


def test_apply_cost_profile_invalid():
    with patch("src.api.v1.endpoints.settings.CostProfileService") as MockService:
        mock_instance = MockService.return_value
        mock_instance.apply_profile.side_effect = ValueError("Unknown cost profile 'bad'")

        resp = client.post("/api/v1/settings/cost-profiles/apply", json={"profile": "bad"})
        assert resp.status_code == 400
        assert "Unknown cost profile" in resp.json()["detail"]


def test_get_onboarding_status_needs_onboarding():
    with patch("src.api.v1.endpoints.settings.CostProfileService") as MockCost, \
         patch("src.api.v1.endpoints.settings.LLMProviderService") as MockProvider:
        MockCost.return_value.get_current_profile.return_value = {"id": "balanced"}
        MockProvider.return_value.list.return_value = [
            {"provider_code": "openrouter", "enabled": True, "api_key_masked": None},
            {"provider_code": "ollama", "enabled": True, "base_url": None},
        ]

        resp = client.get("/api/v1/settings/onboarding-status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "success"
        assert data["needs_onboarding"] is True
        assert data["configured_providers"] == []


def test_get_onboarding_status_configured():
    with patch("src.api.v1.endpoints.settings.CostProfileService") as MockCost, \
         patch("src.api.v1.endpoints.settings.LLMProviderService") as MockProvider:
        MockCost.return_value.get_current_profile.return_value = {"id": "balanced"}
        MockProvider.return_value.list.return_value = [
            {"provider_code": "openrouter", "enabled": True, "api_key_masked": "sk-or-***"},
        ]

        resp = client.get("/api/v1/settings/onboarding-status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "success"
        assert data["needs_onboarding"] is False
        assert data["configured_providers"] == ["openrouter"]


def test_complete_onboarding():
    with patch("src.api.v1.endpoints.settings.CostProfileService") as MockCost, \
         patch("src.api.v1.endpoints.settings.LLMProviderService") as MockProvider:
        mock_provider_instance = MockProvider.return_value
        mock_provider_instance.list.return_value = [
            {"id": "prov-1", "provider_code": "openrouter", "enabled": False}
        ]

        payload = {
            "cost_profile": "balanced",
            "provider_code": "openrouter",
            "api_key": "test",
        }
        resp = client.post("/api/v1/settings/onboarding/complete", json=payload)
        assert resp.status_code == 200
        assert resp.json()["status"] == "success"

        MockCost.return_value.apply_profile.assert_called_once_with("balanced")
        mock_provider_instance.update.assert_called_once_with("prov-1", {
            "enabled": True,
            "api_key": "test",
        })
