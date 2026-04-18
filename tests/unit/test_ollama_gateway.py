"""
Unit tests for OllamaGateway (src/infrastructure/llm/llm_gateway.py).

Tests cover:
  - list_models: parses /api/tags response via parse_ollama_tags
  - ping: success (200) and failure (connection error)
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.infrastructure.llm.llm_gateway import OllamaGateway
from src.domain.interfaces import LLMConfig, PingResult, DiscoveredModel


# ──────────────────────────────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────────────────────────────
@pytest.fixture
def gateway():
    return OllamaGateway()


@pytest.fixture
def config():
    return LLMConfig(
        provider="ollama",
        model="qwen2.5:7b",
        api_key="",
        base_url="http://localhost:11434/v1",
        timeout_seconds=10,
    )


OLLAMA_TAGS_RESPONSE = {
    "models": [
        {
            "name": "qwen2.5:7b",
            "size": 4730000000,
            "details": {
                "parameter_size": "7.6B",
                "family": "qwen2",
                "context_length": 32768,
            },
        },
        {
            "name": "qwen2.5:14b",
            "size": 9000000000,
            "details": {
                "parameter_size": "14.7B",
                "family": "qwen2",
            },
        },
    ]
}


# ──────────────────────────────────────────────────────────────────────
# _strip_v1 helper
# ──────────────────────────────────────────────────────────────────────
def test_strip_v1_removes_suffix():
    assert OllamaGateway._strip_v1("http://localhost:11434/v1") == "http://localhost:11434"


def test_strip_v1_no_suffix():
    assert OllamaGateway._strip_v1("http://localhost:11434") == "http://localhost:11434"


def test_strip_v1_trailing_slash():
    assert OllamaGateway._strip_v1("http://localhost:11434/v1/") == "http://localhost:11434"


def test_strip_v1_none_uses_default():
    result = OllamaGateway._strip_v1(None)
    assert "11434" in result
    assert not result.endswith("/v1")


# ──────────────────────────────────────────────────────────────────────
# list_models
# ──────────────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_list_models_success(gateway, config):
    mock_response = MagicMock()
    mock_response.json.return_value = OLLAMA_TAGS_RESPONSE
    mock_response.raise_for_status = MagicMock()

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.get = AsyncMock(return_value=mock_response)

    with patch("src.infrastructure.llm.llm_gateway.httpx.AsyncClient", return_value=mock_client):
        result = await gateway.list_models(config)

    assert isinstance(result, list)
    assert len(result) == 2
    codes = [m.model_code for m in result]
    assert "qwen2.5:7b" in codes
    assert "qwen2.5:14b" in codes


@pytest.mark.asyncio
async def test_list_models_returns_discovered_model_type(gateway, config):
    mock_response = MagicMock()
    mock_response.json.return_value = OLLAMA_TAGS_RESPONSE
    mock_response.raise_for_status = MagicMock()

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.get = AsyncMock(return_value=mock_response)

    with patch("src.infrastructure.llm.llm_gateway.httpx.AsyncClient", return_value=mock_client):
        result = await gateway.list_models(config)

    for item in result:
        assert isinstance(item, DiscoveredModel)


@pytest.mark.asyncio
async def test_list_models_empty_response(gateway, config):
    mock_response = MagicMock()
    mock_response.json.return_value = {"models": []}
    mock_response.raise_for_status = MagicMock()

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.get = AsyncMock(return_value=mock_response)

    with patch("src.infrastructure.llm.llm_gateway.httpx.AsyncClient", return_value=mock_client):
        result = await gateway.list_models(config)

    assert result == []


# ──────────────────────────────────────────────────────────────────────
# ping
# ──────────────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_ping_success(gateway, config):
    mock_response = MagicMock()
    mock_response.json.return_value = OLLAMA_TAGS_RESPONSE
    mock_response.raise_for_status = MagicMock()

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.get = AsyncMock(return_value=mock_response)

    with patch("src.infrastructure.llm.llm_gateway.httpx.AsyncClient", return_value=mock_client):
        result = await gateway.ping(config)

    assert isinstance(result, PingResult)
    assert result.ok is True
    assert result.latency_ms >= 0
    assert result.error is None
    assert result.detail is not None
    assert result.detail["available_models"] == 2


@pytest.mark.asyncio
async def test_ping_connection_refused(gateway, config):
    import httpx

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.get = AsyncMock(
        side_effect=httpx.ConnectError("Connection refused")
    )

    with patch("src.infrastructure.llm.llm_gateway.httpx.AsyncClient", return_value=mock_client):
        result = await gateway.ping(config)

    assert isinstance(result, PingResult)
    assert result.ok is False
    assert result.error is not None
    assert "Connection refused" in result.error or "refused" in result.error.lower()


@pytest.mark.asyncio
async def test_ping_http_error(gateway, config):
    import httpx

    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock(
        side_effect=httpx.HTTPStatusError(
            "500 Internal Server Error",
            request=MagicMock(),
            response=MagicMock(status_code=500),
        )
    )

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.get = AsyncMock(return_value=mock_response)

    with patch("src.infrastructure.llm.llm_gateway.httpx.AsyncClient", return_value=mock_client):
        result = await gateway.ping(config)

    assert result.ok is False
    assert result.error is not None


# ──────────────────────────────────────────────────────────────────────
# Inheritance: OllamaGateway is a subclass of OpenAIGateway
# ──────────────────────────────────────────────────────────────────────
def test_ollama_gateway_inherits_openai():
    from src.infrastructure.llm.llm_gateway import OpenAIGateway
    assert issubclass(OllamaGateway, OpenAIGateway)


def test_ollama_gateway_registered_in_factory():
    from src.infrastructure.llm.llm_gateway import LLMGatewayFactory
    gw = LLMGatewayFactory.create("ollama")
    assert isinstance(gw, OllamaGateway)
