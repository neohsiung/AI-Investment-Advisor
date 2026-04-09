"""
Unit tests for LoggingLLMGateway.
ILLMGateway Decorator 的單元測試。
"""
import pytest
from unittest.mock import MagicMock, patch
from src.infrastructure.llm.llm_gateway import LoggingLLMGateway
from src.domain.interfaces import Message, LLMConfig

@pytest.fixture
def mock_inner():
    from unittest.mock import AsyncMock
    inner = MagicMock()
    inner.chat = AsyncMock(return_value="test response")
    inner.embed = AsyncMock(return_value=[0.1, 0.2, 0.3])
    inner._last_usage = {"prompt_tokens": 100, "completion_tokens": 50}
    return inner

@pytest.fixture
def logging_gateway(mock_inner):
    return LoggingLLMGateway(
        inner=mock_inner,
        agent_name="TestAgent",
        tier="fast",
        user_id="test@example.com",
    )

class TestLoggingLLMGateway:
    @pytest.mark.asyncio
    async def test_returns_inner_chat_content(self, logging_gateway, mock_inner):
        """回傳值應等於 inner.chat() 的回傳值"""
        messages = [Message(role="user", content="test")]
        config = LLMConfig(provider="OpenRouter", model="gpt-4o", api_key="sk-123")
        result = await logging_gateway.chat(messages, config)
        assert result == "test response"

    @pytest.mark.asyncio
    async def test_logs_usage_after_chat(self, logging_gateway, mock_inner):
        """chat() 後 UsageRepository.log_usage() 應被呼叫"""
        messages = [Message(role="user", content="test")]
        config = LLMConfig(provider="OpenRouter", model="gpt-4o", api_key="sk-123")
    
        import asyncio
        with patch("src.repositories.usage_repository.UsageRepository.log_usage") as mock_log:
            await logging_gateway.chat(messages, config)
            # Give background task a moment to execute
            await asyncio.sleep(0.1)
            mock_log.assert_called_once_with(
                user_id="test@example.com",
                agent_name="TestAgent",
                tier="fast",
                model="gpt-4o",
                provider="OpenRouter",
                prompt_tokens=100,
                completion_tokens=50,
                metadata={}
            )

    @pytest.mark.asyncio
    async def test_no_usage_metadata_skips_logging(self, logging_gateway, mock_inner):
        """若 inner 沒有 _last_usage，不呼叫 logger"""
        if hasattr(mock_inner, "_last_usage"):
            delattr(mock_inner, "_last_usage")
        
        messages = [Message(role="user", content="test")]
        config = LLMConfig(provider="OpenRouter", model="gpt-4o", api_key="sk-123")
    
        with patch("src.repositories.usage_repository.UsageRepository.log_usage") as mock_log:
            await logging_gateway.chat(messages, config)
            mock_log.assert_not_called()

    @pytest.mark.asyncio
    async def test_logging_failure_does_not_raise(self, logging_gateway, mock_inner):
        """Usage Repository 失敗時，主流程不中斷"""
        messages = [Message(role="user", content="test")]
        config = LLMConfig(provider="OpenRouter", model="gpt-4o", api_key="sk-123")
    
        with patch("src.repositories.usage_repository.UsageRepository.log_usage") as mock_log:
            mock_log.side_effect = Exception("DB down")
            # Should NOT raise
            result = await logging_gateway.chat(messages, config)
            assert result == "test response"

    @pytest.mark.asyncio
    async def test_embed_passes_through(self, logging_gateway, mock_inner):
        """embed() 應直接轉發給 inner，不影響 usage logger"""
        mock_inner.embed.return_value = [0.1, 0.2, 0.3]
        config = LLMConfig(provider="OpenRouter", model="gpt-4o", api_key="sk-123")
        result = await logging_gateway.embed("some text", config)
        assert result == [0.1, 0.2, 0.3]
        mock_inner.embed.assert_called_once()
