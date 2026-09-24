"""
Tests for Issue Routing API endpoints.
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock

from src.api.v1.endpoints.llm_settings import router
from src.api.v1.dependencies import get_current_user_id


@pytest.fixture
def app():
    fastapi_app = FastAPI()
    fastapi_app.include_router(router, prefix="/api/v1/settings/llm")
    fastapi_app.dependency_overrides[get_current_user_id] = lambda: "test_user_api"
    return fastapi_app


@pytest.fixture
def client(app):
    return TestClient(app)


def test_list_issue_routing_endpoint(client):
    """Verify GET /api/v1/settings/llm/issue-routing returns default specs."""
    response = client.get("/api/v1/settings/llm/issue-routing")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert len(data["data"]) >= 10

    # Ensure reflex tier items exist
    issue_types = {item["issue_type"]: item for item in data["data"]}
    assert "intent_routing" in issue_types
    assert issue_types["intent_routing"]["default_tier"] == "reflex"
    assert issue_types["intent_routing"]["is_reflex_eligible"] is True


def test_update_issue_routing_endpoint(client):
    """Verify PUT /api/v1/settings/llm/issue-routing/{issue_type} updates overrides."""
    store = {}

    def mock_get(user_id, key, default=None):
        return store.get(key, default)

    def mock_set(user_id, key, value):
        store[key] = value

    with patch("src.repositories.settings_repository.AlchemySettingsRepository.set", side_effect=mock_set) as mock_s, \
         patch("src.repositories.settings_repository.AlchemySettingsRepository.get", side_effect=mock_get):

        payload = {
            "default_tier": "fast",
            "confidence_threshold": 0.95
        }
        response = client.put("/api/v1/settings/llm/issue-routing/intent_routing", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data["issue_type"] == "intent_routing"
        assert data["default_tier"] == "fast"
        assert data["confidence_threshold"] == 0.95
        assert "issue_tier_overrides" in store
