import pytest
from unittest.mock import patch, MagicMock
from src.services.readwise_service import ReadwiseService
from src.data.providers.readwise_provider import ReadwiseProvider

@pytest.fixture
def mock_settings_service():
    with patch("src.data.providers.readwise_provider.SettingsService") as mock:
        instance = mock.return_value
        instance.get_all_settings.return_value = {"READWISE_API_KEY": "fake_key"}
        yield instance

@pytest.fixture
def mock_agent_factory():
    with patch("src.services.readwise_service.AgentFactory") as mock:
        agent_instance = MagicMock()
        mock.create_agent.return_value = agent_instance
        # Mock LLM response
        agent_instance._call_real_llm.return_value = '{"is_investment_related": true, "requires_action": true, "reasoning": "This is about AAPL stock.", "suggested_action": "Buy AAPL"}'
        yield mock

def test_readwise_provider_fetch(mock_settings_service):
    with patch("src.data.providers.readwise_provider.requests.get") as mock_get:
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "count": 1,
            "next": None,
            "previous": None,
            "results": [
                {
                    "id": 1,
                    "text": "Test Highlight",
                    "note": "Test Note",
                    "book_id": 123
                }
            ]
        }
        mock_get.return_value = mock_resp
        
        provider = ReadwiseProvider(user_id="test_user")
        results = provider.fetch_highlights()
        
        assert len(results) == 1
        assert results[0]["text"] == "Test Highlight"
        mock_get.assert_called_once()

def test_readwise_service_analyze(mock_settings_service, mock_agent_factory):
    with patch.object(ReadwiseProvider, "fetch_highlights") as mock_fetch:
        mock_fetch.return_value = [
            {
                "id": 101,
                "text": "Always buy low.",
                "note": "Good tip",
                "book_id": 999,
                "url": "http://example.com"
            }
        ]
        
        service = ReadwiseService(user_id="test_user")
        analyzed = service.fetch_and_analyze_highlights()
        
        assert len(analyzed) == 1
        assert analyzed[0]["id"] == 101
        assert analyzed[0]["analysis"]["is_investment_related"] is True
        assert analyzed[0]["analysis"]["requires_action"] is True
        assert analyzed[0]["book_id"] == 999
        
        agent_instance = mock_agent_factory.create_agent.return_value
        agent_instance._call_real_llm.assert_called_once()
        call_arg = agent_instance._call_real_llm.call_args[0][0]
        assert "Always buy low." in call_arg
