"""
Tests for Channel Adapters - GoogleChatAdapter and EmailAdapter coverage.
補充 channel adapters 的測試覆蓋率。
"""
import pytest
import asyncio
from unittest.mock import MagicMock, patch, AsyncMock
from src.infrastructure.channels.google_chat_adapter import GoogleChatAdapter
from src.infrastructure.channels.email_adapter import EmailAdapter


# ─────────────────────────────────────────────
# GoogleChatAdapter Tests
# ─────────────────────────────────────────────

class TestGoogleChatAdapterInit:
    """Test GoogleChatAdapter initialization."""

    def test_init_with_webhook_url(self):
        adapter = GoogleChatAdapter(webhook_url="https://chat.googleapis.com/v1/spaces/test")
        assert adapter.webhook_url == "https://chat.googleapis.com/v1/spaces/test"
        assert adapter.is_active is True

    def test_init_without_webhook_url_is_inactive(self):
        with patch.dict("os.environ", {}, clear=True):
            adapter = GoogleChatAdapter(webhook_url=None)
            # GOOGLE_CHAT_WEBHOOK_URL not set → empty → inactive
            assert adapter.is_active is False

    def test_init_strips_whitespace(self):
        adapter = GoogleChatAdapter(webhook_url="  https://chat.googleapis.com/test  ")
        assert adapter.webhook_url == "https://chat.googleapis.com/test"

    def test_init_from_env(self):
        with patch.dict("os.environ", {"GOOGLE_CHAT_WEBHOOK_URL": "https://env-webhook.example.com"}):
            adapter = GoogleChatAdapter()
            assert adapter.webhook_url == "https://env-webhook.example.com"
            assert adapter.is_active is True


class TestGoogleChatAdapterSendMessage:
    """Test GoogleChatAdapter.send_message."""

    @pytest.mark.asyncio
    async def test_send_message_with_string_calls_send_alert(self):
        adapter = GoogleChatAdapter(webhook_url="https://chat.googleapis.com/test")
        adapter.send_alert = AsyncMock(return_value=True)
        result = await adapter.send_message("user1", "Hello World")
        adapter.send_alert.assert_called_once_with("user1", "Message", "Hello World")
        assert result is True

    @pytest.mark.asyncio
    async def test_send_message_with_non_string_returns_false(self):
        adapter = GoogleChatAdapter(webhook_url="https://chat.googleapis.com/test")
        result = await adapter.send_message("user1", {"key": "value"})
        assert result is False


class TestGoogleChatAdapterReceiveCommand:
    """Test GoogleChatAdapter.receive_command."""

    @pytest.mark.asyncio
    async def test_receive_command_returns_none(self):
        adapter = GoogleChatAdapter(webhook_url="https://chat.googleapis.com/test")
        result = await adapter.receive_command({"payload": "data"})
        assert result is None


class TestGoogleChatAdapterAuthenticate:
    """Test GoogleChatAdapter.authenticate."""

    @pytest.mark.asyncio
    async def test_authenticate_returns_true(self):
        adapter = GoogleChatAdapter(webhook_url="https://chat.googleapis.com/test")
        result = await adapter.authenticate(MagicMock())
        assert result is True


class TestGoogleChatAdapterSendAlert:
    """Test GoogleChatAdapter.send_alert."""

    @pytest.mark.asyncio
    async def test_send_alert_no_webhook_url_returns_false(self):
        with patch.dict("os.environ", {}, clear=True):
            adapter = GoogleChatAdapter(webhook_url="")
            result = await adapter.send_alert("user1", "Title", "Content")
            assert result is False

    @pytest.mark.asyncio
    async def test_send_alert_success(self):
        adapter = GoogleChatAdapter(webhook_url="https://chat.googleapis.com/test")
        mock_response = MagicMock()
        mock_response.status_code = 200

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=mock_response)

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await adapter.send_alert("user1", "Test Title", "Test Content")
        assert result is True

    @pytest.mark.asyncio
    async def test_send_alert_api_error_returns_false(self):
        adapter = GoogleChatAdapter(webhook_url="https://chat.googleapis.com/test")
        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.text = "Bad Request"

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=mock_response)

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await adapter.send_alert("user1", "Title", "Content")
        assert result is False

    @pytest.mark.asyncio
    async def test_send_alert_exception_returns_false(self):
        adapter = GoogleChatAdapter(webhook_url="https://chat.googleapis.com/test")

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(side_effect=Exception("Network error"))

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await adapter.send_alert("user1", "Title", "Content")
        assert result is False

    @pytest.mark.asyncio
    async def test_send_alert_formats_message_correctly(self):
        adapter = GoogleChatAdapter(webhook_url="https://chat.googleapis.com/test")
        mock_response = MagicMock()
        mock_response.status_code = 200

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=mock_response)

        with patch("httpx.AsyncClient", return_value=mock_client):
            await adapter.send_alert("user1", "My Title", "My Content")

        call_kwargs = mock_client.post.call_args
        payload = call_kwargs.kwargs.get("json") or call_kwargs[1].get("json")
        assert "*My Title*" in payload["text"]
        assert "My Content" in payload["text"]


class TestGoogleChatAdapterHandleWebhook:
    """Test GoogleChatAdapter.handle_webhook."""

    @pytest.mark.asyncio
    async def test_handle_webhook_returns_ok(self):
        adapter = GoogleChatAdapter(webhook_url="https://chat.googleapis.com/test")
        result = await adapter.handle_webhook({"event": "test"})
        assert result == {"ok": True}


# ─────────────────────────────────────────────
# EmailAdapter Tests
# ─────────────────────────────────────────────

class TestEmailAdapterInit:
    """Test EmailAdapter initialization."""

    def test_init_with_smtp_config(self):
        smtp_config = {
            "smtp_host": "smtp.example.com",
            "smtp_port": 587,
            "sender_email": "test@example.com",
            "sender_password": "password"
        }
        with patch("src.infrastructure.channels.email_adapter.EmailNotifier") as mock_notifier_cls:
            mock_notifier = MagicMock()
            mock_notifier_cls.return_value = mock_notifier
            adapter = EmailAdapter(smtp_config=smtp_config)
            mock_notifier_cls.assert_called_once_with(smtp_config=smtp_config)
            assert adapter.is_active is True

    def test_init_without_smtp_config_uses_env(self):
        with patch("src.infrastructure.channels.email_adapter.EmailNotifier") as mock_notifier_cls:
            mock_notifier = MagicMock()
            mock_notifier.sender_email = "test@example.com"
            mock_notifier.sender_password = "password"
            mock_notifier_cls.return_value = mock_notifier
            adapter = EmailAdapter()
            mock_notifier_cls.assert_called_once_with()
            assert adapter.is_active is True

    def test_init_without_smtp_config_inactive_when_no_credentials(self):
        with patch("src.infrastructure.channels.email_adapter.EmailNotifier") as mock_notifier_cls:
            mock_notifier = MagicMock()
            mock_notifier.sender_email = ""
            mock_notifier.sender_password = ""
            mock_notifier_cls.return_value = mock_notifier
            adapter = EmailAdapter()
            assert adapter.is_active is False


class TestEmailAdapterSendMessage:
    """Test EmailAdapter.send_message."""

    @pytest.mark.asyncio
    async def test_send_message_with_string_calls_send_alert(self):
        with patch("src.infrastructure.channels.email_adapter.EmailNotifier"):
            adapter = EmailAdapter()
            adapter.send_alert = AsyncMock(return_value=True)
            result = await adapter.send_message("user@example.com", "Hello")
            adapter.send_alert.assert_called_once_with("user@example.com", "Message", "Hello")
            assert result is True

    @pytest.mark.asyncio
    async def test_send_message_with_non_string_returns_false(self):
        with patch("src.infrastructure.channels.email_adapter.EmailNotifier"):
            adapter = EmailAdapter()
            result = await adapter.send_message("user@example.com", {"key": "value"})
            assert result is False


class TestEmailAdapterReceiveCommand:
    """Test EmailAdapter.receive_command."""

    @pytest.mark.asyncio
    async def test_receive_command_returns_none(self):
        with patch("src.infrastructure.channels.email_adapter.EmailNotifier"):
            adapter = EmailAdapter()
            result = await adapter.receive_command({"payload": "data"})
            assert result is None


class TestEmailAdapterAuthenticate:
    """Test EmailAdapter.authenticate."""

    @pytest.mark.asyncio
    async def test_authenticate_returns_true(self):
        with patch("src.infrastructure.channels.email_adapter.EmailNotifier"):
            adapter = EmailAdapter()
            result = await adapter.authenticate(MagicMock())
            assert result is True


class TestEmailAdapterSendAlert:
    """Test EmailAdapter.send_alert."""

    @pytest.mark.asyncio
    async def test_send_alert_basic(self):
        with patch("src.infrastructure.channels.email_adapter.EmailNotifier") as mock_notifier_cls:
            mock_notifier = MagicMock()
            mock_notifier.send_report = AsyncMock(return_value=True)
            mock_notifier_cls.return_value = mock_notifier
            adapter = EmailAdapter()
            result = await adapter.send_alert("user@example.com", "Test Title", "Test Content")
            assert result is True
            mock_notifier.send_report.assert_called_once_with("Test Title", "Test Content", to_email="user@example.com")

    @pytest.mark.asyncio
    async def test_send_alert_with_actions_appends_to_body(self):
        with patch("src.infrastructure.channels.email_adapter.EmailNotifier") as mock_notifier_cls:
            mock_notifier = MagicMock()
            mock_notifier.send_report = AsyncMock(return_value=True)
            mock_notifier_cls.return_value = mock_notifier
            adapter = EmailAdapter()
            actions = [
                {"label": "View Portfolio", "data": "action=view"},
                {"label": "eToro Link", "data": "action=etoro_link"},
            ]
            result = await adapter.send_alert("user@example.com", "Title", "Content", actions=actions)
            assert result is True
            call_args = mock_notifier.send_report.call_args
            body = call_args[0][1]  # second positional arg
            assert "Actions" in body
            assert "View Portfolio" in body
            assert "https://www.etoro.com/watchlists" in body

    @pytest.mark.asyncio
    async def test_send_alert_with_category_override(self):
        with patch("src.infrastructure.channels.email_adapter.EmailNotifier") as mock_notifier_cls:
            mock_notifier = MagicMock()
            mock_notifier.send_report = AsyncMock(return_value=True)
            mock_notifier_cls.return_value = mock_notifier
            adapter = EmailAdapter()

            mock_filter = MagicMock()
            mock_filter.get_recipient_override.return_value = "override@example.com"

            result = await adapter.send_alert(
                "user@example.com", "Title", "Content",
                category="report", _filter=mock_filter
            )
            assert result is True
            mock_notifier.send_report.assert_called_once_with("Title", "Content", to_email="override@example.com")

    @pytest.mark.asyncio
    async def test_send_alert_with_to_email_kwarg(self):
        with patch("src.infrastructure.channels.email_adapter.EmailNotifier") as mock_notifier_cls:
            mock_notifier = MagicMock()
            mock_notifier.send_report = AsyncMock(return_value=True)
            mock_notifier_cls.return_value = mock_notifier
            adapter = EmailAdapter()
            result = await adapter.send_alert(
                "user@example.com", "Title", "Content",
                to_email="specific@example.com"
            )
            assert result is True
            mock_notifier.send_report.assert_called_once_with("Title", "Content", to_email="specific@example.com")

    @pytest.mark.asyncio
    async def test_send_alert_with_category_no_filter(self):
        """Category set but no _filter → override_to stays None."""
        with patch("src.infrastructure.channels.email_adapter.EmailNotifier") as mock_notifier_cls:
            mock_notifier = MagicMock()
            mock_notifier.send_report = AsyncMock(return_value=True)
            mock_notifier_cls.return_value = mock_notifier
            adapter = EmailAdapter()
            result = await adapter.send_alert(
                "user@example.com", "Title", "Content",
                category="sentinel"
            )
            assert result is True
            mock_notifier.send_report.assert_called_once_with("Title", "Content", to_email="user@example.com")
