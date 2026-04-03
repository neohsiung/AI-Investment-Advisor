import unittest
from unittest.mock import MagicMock, patch
from src.infrastructure.llm.llm_gateway import LoggingLLMGateway, OpenRouterGateway
from src.domain.interfaces import Message, LLMConfig


class TestLoggingLLMGateway(unittest.TestCase):
    def setUp(self):
        self.mock_inner = MagicMock()
        self.gateway = LoggingLLMGateway(
            inner=self.mock_inner,
            agent_name="TestAgent",
            tier="fast",
            user_id="user@example.com"
        )
        self.messages = [Message(role="user", content="Hello")]
        self.config = LLMConfig(provider="OpenRouter", model="gpt-4o-mini", api_key="sk-123")

    @patch("src.services.token_logger_service.TokenLoggerService")
    def test_chat_logs_usage(self, mock_logger_class):
        # 1. Setup mock inner gateway to return content and set _last_usage
        self.mock_inner.chat.return_value = "World"
        self.mock_inner._last_usage = {
            "prompt_tokens": 10,
            "completion_tokens": 5,
            "total_tokens": 15
        }
        
        mock_logger_inst = mock_logger_class.return_value
        
        # 2. Call chat
        result = self.gateway.chat(self.messages, self.config)
        
        # 3. Verify
        self.assertEqual(result, "World")
        self.mock_inner.chat.assert_called_once_with(self.messages, self.config)
        
        # 4. Verify logging service was called correctly
        mock_logger_inst.log_usage.assert_called_once_with(
            user_id="user@example.com",
            agent_name="TestAgent",
            tier="fast",
            model="gpt-4o-mini",
            provider="OpenRouter",
            prompt_tokens=10,
            completion_tokens=5,
            metadata={}
        )

    @patch("src.services.token_logger_service.TokenLoggerService")
    def test_chat_no_usage_metadata(self, mock_logger_class):
        # 1. Setup mock inner gateway without _last_usage
        self.mock_inner.chat.return_value = "World"
        if hasattr(self.mock_inner, "_last_usage"):
            delattr(self.mock_inner, "_last_usage")
        
        mock_logger_inst = mock_logger_class.return_value
        
        # 2. Call chat
        result = self.gateway.chat(self.messages, self.config)
        
        # 3. Verify logging was NOT called
        self.assertEqual(result, "World")
        mock_logger_inst.log_usage.assert_not_called()

    @patch("src.services.token_logger_service.TokenLoggerService")
    def test_logging_failure_does_not_break_flow(self, mock_logger_class):
        # 1. Setup logging service to raise exception
        self.mock_inner.chat.return_value = "World"
        self.mock_inner._last_usage = {"prompt_tokens": 1, "completion_tokens": 1}
        
        mock_logger_inst = mock_logger_class.return_value
        mock_logger_inst.log_usage.side_effect = Exception("DB Down")
        
        # 2. Call chat (should not raise)
        result = self.gateway.chat(self.messages, self.config)
        
        # 3. Verify result is still returned
        self.assertEqual(result, "World")


if __name__ == "__main__":
    unittest.main()
