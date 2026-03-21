"""
Unit tests for LLM Gateway infrastructure layer.
LLM 閘道基礎設施層單元測試。

Tests:
  - OpenRouterGateway / GeminiGateway / OpenAIGateway chat + embed
  - LLMGatewayFactory provider routing
  - RetryLLMGateway exponential backoff
  - MockLLMGateway simulation mode
  - BaseAgent DI integration with ILLMGateway
"""

import pytest
from unittest.mock import MagicMock, patch, Mock
from src.domain.interfaces import ILLMGateway, Message, LLMConfig
from src.infrastructure.llm.llm_gateway import (
    OpenRouterGateway,
    GeminiGateway,
    OpenAIGateway,
    LLMGatewayFactory,
    RetryLLMGateway,
    MockLLMGateway,
)


# ============================================================
# Value Object Tests
# ============================================================

class TestMessage:
    def test_immutable(self):
        msg = Message(role="user", content="hello")
        assert msg.role == "user"
        assert msg.content == "hello"
        with pytest.raises(AttributeError):
            msg.role = "system"

    def test_equality(self):
        m1 = Message(role="system", content="hi")
        m2 = Message(role="system", content="hi")
        assert m1 == m2


class TestLLMConfig:
    def test_defaults(self):
        config = LLMConfig(provider="OpenRouter", model="gpt-4")
        assert config.temperature == 0.7
        assert config.max_retries == 3
        assert config.timeout_seconds == 30
        assert config.api_key == ""

    def test_custom(self):
        config = LLMConfig(
            provider="OpenAI", model="gpt-3.5", api_key="sk-test",
            temperature=0.5, max_retries=5
        )
        assert config.api_key == "sk-test"
        assert config.max_retries == 5


# ============================================================
# Gateway Tests (mocked HTTP)
# ============================================================

@pytest.fixture
def sample_messages():
    return [
        Message(role="system", content="You are a test assistant."),
        Message(role="user", content="What is 2+2?"),
    ]

@pytest.fixture
def sample_config():
    return LLMConfig(
        provider="OpenRouter",
        model="test-model",
        api_key="test-key",
        base_url="",
        temperature=0.5,
    )


class TestOpenRouterGateway:
    @patch("src.infrastructure.llm.llm_gateway.requests.post")
    def test_chat_success(self, mock_post, sample_messages, sample_config):
        mock_response = Mock()
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "4"}}]
        }
        mock_response.raise_for_status = Mock()
        mock_post.return_value = mock_response

        gateway = OpenRouterGateway()
        result = gateway.chat(sample_messages, sample_config)

        assert result == "4"
        mock_post.assert_called_once()
        call_args = mock_post.call_args
        assert call_args[1]["json"]["model"] == "test-model"
        assert len(call_args[1]["json"]["messages"]) == 2

    @patch("src.infrastructure.llm.llm_gateway.requests.post")
    def test_chat_auth_header(self, mock_post, sample_messages, sample_config):
        mock_response = Mock()
        mock_response.json.return_value = {"choices": [{"message": {"content": "ok"}}]}
        mock_response.raise_for_status = Mock()
        mock_post.return_value = mock_response

        gateway = OpenRouterGateway()
        gateway.chat(sample_messages, sample_config)

        headers = mock_post.call_args[1]["headers"]
        assert "Bearer test-key" in headers["Authorization"]


class TestGeminiGateway:
    @patch("src.infrastructure.llm.llm_gateway.requests.post")
    def test_chat_success(self, mock_post, sample_messages):
        config = LLMConfig(provider="Google Gemini", model="gemini-1.5-pro", api_key="gem-key")
        mock_response = Mock()
        mock_response.json.return_value = {
            "candidates": [{"content": {"parts": [{"text": "Hello from Gemini"}]}}]
        }
        mock_response.raise_for_status = Mock()
        mock_post.return_value = mock_response

        gateway = GeminiGateway()
        result = gateway.chat(sample_messages, config)

        assert result == "Hello from Gemini"
        # Verify model prefix
        call_url = mock_post.call_args[0][0]
        assert "models/gemini-1.5-pro" in call_url

    @patch("src.infrastructure.llm.llm_gateway.requests.post")
    def test_chat_with_models_prefix(self, mock_post, sample_messages):
        config = LLMConfig(provider="Google Gemini", model="models/gemini-flash", api_key="key")
        mock_response = Mock()
        mock_response.json.return_value = {
            "candidates": [{"content": {"parts": [{"text": "ok"}]}}]
        }
        mock_response.raise_for_status = Mock()
        mock_post.return_value = mock_response

        gateway = GeminiGateway()
        gateway.chat(sample_messages, config)

        call_url = mock_post.call_args[0][0]
        assert "models/models/" not in call_url  # No double prefix


class TestOpenAIGateway:
    @patch("src.infrastructure.llm.llm_gateway.requests.post")
    def test_chat_success(self, mock_post, sample_messages):
        config = LLMConfig(provider="OpenAI", model="gpt-4", api_key="sk-test")
        mock_response = Mock()
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "OpenAI response"}}]
        }
        mock_response.raise_for_status = Mock()
        mock_post.return_value = mock_response

        gateway = OpenAIGateway()
        result = gateway.chat(sample_messages, config)

        assert result == "OpenAI response"


# ============================================================
# Factory Tests
# ============================================================

class TestLLMGatewayFactory:
    def test_create_openrouter(self):
        gw = LLMGatewayFactory.create("OpenRouter")
        assert isinstance(gw, OpenRouterGateway)

    def test_create_gemini(self):
        gw = LLMGatewayFactory.create("Google Gemini")
        assert isinstance(gw, GeminiGateway)

    def test_create_gemini_alias(self):
        gw = LLMGatewayFactory.create("gemini")
        assert isinstance(gw, GeminiGateway)

    def test_create_openai(self):
        gw = LLMGatewayFactory.create("OpenAI")
        assert isinstance(gw, OpenAIGateway)

    def test_unsupported_provider_raises(self):
        with pytest.raises(ValueError, match="Unsupported LLM provider"):
            LLMGatewayFactory.create("UnknownProvider")

    def test_register_custom_provider(self):
        class CustomGateway(ILLMGateway):
            def chat(self, messages, config): return "custom"
            def embed(self, text, config): return [1.0]

        LLMGatewayFactory.register("CustomTest", CustomGateway)
        gw = LLMGatewayFactory.create("CustomTest")
        assert isinstance(gw, CustomGateway)
        # Clean up
        del LLMGatewayFactory._REGISTRY["CustomTest"]


# ============================================================
# RetryLLMGateway Tests
# ============================================================

class TestRetryLLMGateway:
    def test_retry_success_after_failure(self):
        inner = MagicMock(spec=ILLMGateway)
        inner.chat.side_effect = [Exception("fail"), "success"]

        gateway = RetryLLMGateway(inner, max_retries=3)
        with patch("src.infrastructure.llm.llm_gateway.time.sleep"):
            result = gateway.chat([], LLMConfig(provider="x", model="y"))

        assert result == "success"
        assert inner.chat.call_count == 2

    def test_retry_exhausted_raises(self):
        inner = MagicMock(spec=ILLMGateway)
        inner.chat.side_effect = Exception("persistent failure")

        gateway = RetryLLMGateway(inner, max_retries=2)
        with patch("src.infrastructure.llm.llm_gateway.time.sleep"):
            with pytest.raises(Exception, match="persistent failure"):
                gateway.chat([], LLMConfig(provider="x", model="y"))

        assert inner.chat.call_count == 2


# ============================================================
# MockLLMGateway Tests
# ============================================================

class TestMockLLMGateway:
    def test_default_response(self):
        config = LLMConfig(provider="Test", model="test-model")
        msgs = [Message(role="user", content="hi")]

        gw = MockLLMGateway()
        result = gw.chat(msgs, config)

        assert "Simulation Mode" in result
        assert "test-model" in result

    def test_custom_response(self):
        gw = MockLLMGateway(default_response="custom output")
        result = gw.chat([], LLMConfig(provider="x", model="y"))
        assert result == "custom output"

    def test_embed_returns_zero_vector(self):
        gw = MockLLMGateway()
        vec = gw.embed("test", LLMConfig(provider="x", model="y"))
        assert len(vec) == 1536
        assert all(v == 0.0 for v in vec)


# ============================================================
# BaseAgent DI Integration
# ============================================================

class TestBaseAgentGatewayDI:
    """Test that BaseAgent correctly uses injected ILLMGateway."""

    @patch('src.agents.base_agent.BaseAgent._load_prompt', return_value="Test Prompt")
    def test_injected_gateway_is_used(self, _):
        from src.agents.base_agent import BaseAgent

        class TestAgent(BaseAgent):
            def run(self, context, mode=None):
                return "test"

        mock_gateway = MagicMock(spec=ILLMGateway)
        mock_gateway.chat.return_value = "Gateway Response"

        mock_settings = MagicMock()
        mock_settings.get_all.return_value = []

        agent = TestAgent(
            name="TestDI",
            prompt_path="dummy",
            use_cache=False,
            user_id="test_user",
            settings_repo=mock_settings,
            llm_gateway=mock_gateway,
        )

        messages = [
            {"role": "system", "content": "sys"},
            {"role": "user", "content": "hello"},
        ]
        result = agent.call_llm(messages)

        assert result == "Gateway Response"
        mock_gateway.chat.assert_called_once()

    @patch('src.agents.base_agent.BaseAgent._load_prompt', return_value="Test Prompt")
    def test_default_gateway_fallback_to_mock(self, _):
        """When no API key, should create MockLLMGateway automatically."""
        from src.agents.base_agent import BaseAgent

        class TestAgent(BaseAgent):
            def run(self, context, mode=None):
                return "test"

        mock_settings = MagicMock()
        mock_settings.get_all.return_value = []

        agent = TestAgent(
            name="TestFallback",
            prompt_path="dummy",
            use_cache=False,
            user_id="test_user",
            settings_repo=mock_settings,
        )

        # Should have a MockLLMGateway since no API key
        assert isinstance(agent._llm_gateway, MockLLMGateway)

    @patch('src.agents.base_agent.BaseAgent._load_prompt', return_value="Test Prompt")
    def test_legacy_mock_llm_call_bridges(self, _):
        """Verify _mock_llm_call bridges to call_llm -> gateway."""
        from src.agents.base_agent import BaseAgent

        class TestAgent(BaseAgent):
            def run(self, context, mode=None):
                return "test"

        mock_gateway = MagicMock(spec=ILLMGateway)
        mock_gateway.chat.return_value = "Bridge Response"

        mock_settings = MagicMock()
        mock_settings.get_all.return_value = []

        agent = TestAgent(
            name="TestBridge",
            prompt_path="dummy",
            use_cache=False,
            user_id="test_user",
            settings_repo=mock_settings,
            llm_gateway=mock_gateway,
        )

        result = agent._mock_llm_call("user prompt", "system prompt")
        assert result == "Bridge Response"
        mock_gateway.chat.assert_called_once()
