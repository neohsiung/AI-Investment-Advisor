"""
Tests for notification user_id resolution logic.
測試通知的 user_id 解析邏輯。

Covers:
1. SentinelService._do_send_alert uses internal user_id in HTTP payload
2. Notification microservice resolves channel-specific IDs to internal user_id
"""
import pytest
from unittest.mock import MagicMock, AsyncMock, patch


@pytest.fixture
def anyio_backend():
    return 'asyncio'


# ─────────────────────────────────────────────────────
# Test 1: SentinelService uses internal user_id
# ─────────────────────────────────────────────────────

@pytest.mark.anyio
async def test_do_send_alert_uses_internal_user_id():
    """
    Verify _do_send_alert sends the internal user_id (from settings_service),
    NOT the LINE_USER_ID env var, to the notification microservice.
    確認 _do_send_alert 使用內部 user_id 而非 LINE_USER_ID 環境變數。
    """
    with patch('src.services.sentinel_service.AlchemySentinelRepository') as mock_repo_cls:
        mock_repo = mock_repo_cls.return_value
        mock_repo.is_duplicate_alert.return_value = False

        from src.services.sentinel_service import SentinelService
        from src.services.settings_service import SettingsService
        from src.services.council_service import CouncilService

        mock_settings = MagicMock(spec=SettingsService)
        mock_settings.user_id = "alice@example.com"  # Internal user ID

        mock_council = MagicMock(spec=CouncilService)
        mock_council.start_session = AsyncMock(
            return_value={"consensus": "SELL immediately — danger detected."}
        )

        sentinel = SentinelService(
            user_id="alice@example.com",
            settings_service=mock_settings,
            council_service=mock_council,
        )

        triggers = [{"id": "vix_spike", "text": "🔴 VIX Spike: 45.0 > 30.0"}]

        with patch('src.services.sentinel_service.NotificationService') as mock_noti_cls, \
             patch('src.services.sentinel_service.NotificationSettingsManager') as mock_nsm_cls:
            
            mock_noti_instance = MagicMock()
            mock_noti_instance.notify_all = AsyncMock(return_value={})
            mock_noti_cls.create_with_settings.return_value = mock_noti_instance
            
            mock_nsm = MagicMock()
            mock_nsm.get_active_notification_channels.return_value = ["email"]
            mock_nsm_cls.return_value = mock_nsm

            await sentinel._do_send_alert(triggers, source="Sentinel")

            # Verify: NotificationService was created with the INTERNAL user_id
            mock_noti_cls.create_with_settings.assert_called_once()
            call_kwargs = mock_noti_cls.create_with_settings.call_args.kwargs
            assert call_kwargs["user_id"] == "alice@example.com", (
                f"Expected internal user_id 'alice@example.com', got '{call_kwargs['user_id']}'"
            )


# ─────────────────────────────────────────────────────
# Test 2: Microservice resolves channel-specific ID
# ─────────────────────────────────────────────────────

@pytest.mark.anyio
async def test_process_notification_resolves_channel_id():
    """
    Verify the notification microservice resolves a LINE User ID
    to the internal user_id via find_user_by_channel_id fallback.
    確認微服務能從 LINE User ID 反查出內部 user_id。
    """
    from services.notification.src.app.main import NotificationRequest, _process_notification

    req = NotificationRequest(
        user_id="U1a2b3c4d5e6f",  # LINE-specific User ID
        title="Test Alert",
        content="Test content",
        channels=["line"],
        category="sentinel",
    )

    with patch('services.notification.src.app.main.SettingsService') as mock_svc_cls, \
         patch('services.notification.src.app.main.NotificationService') as mock_noti_cls:

        # First call: no channel settings found (wrong user_id)
        mock_svc_empty = MagicMock()
        mock_svc_empty.get_all_settings.return_value = {}
        mock_svc_empty.find_user_by_channel_id.return_value = "alice@example.com"

        # Second call: correct settings found
        mock_svc_resolved = MagicMock()
        mock_svc_resolved.get_all_settings.return_value = {
            "channel_line_enabled": "true",
            "channel_line_access_token": "tok_xxx",
        }

        mock_svc_cls.side_effect = [mock_svc_empty, mock_svc_resolved]

        mock_noti_instance = MagicMock()
        mock_noti_instance.notify_all = AsyncMock(return_value={})
        mock_noti_cls.create_with_settings.return_value = mock_noti_instance

        await _process_notification(req)

        # Verify: find_user_by_channel_id was called with the LINE User ID
        mock_svc_empty.find_user_by_channel_id.assert_called_once_with("U1a2b3c4d5e6f")

        # Verify: NotificationService was created with the RESOLVED internal user_id
        mock_noti_cls.create_with_settings.assert_called_once_with(
            settings_service=mock_svc_resolved,
            user_id="alice@example.com",
        )


@pytest.mark.anyio
async def test_process_notification_direct_user_id():
    """
    Verify the notification microservice works directly when
    the incoming user_id already has channel settings.
    確認當傳入的 user_id 已有設定時，不會觸發 fallback。
    """
    from services.notification.src.app.main import NotificationRequest, _process_notification

    req = NotificationRequest(
        user_id="alice@example.com",
        title="Test Alert",
        content="Test content",
        channels=["line", "email"],
        category="sentinel",
    )

    with patch('services.notification.src.app.main.SettingsService') as mock_svc_cls, \
         patch('services.notification.src.app.main.NotificationService') as mock_noti_cls:

        mock_svc = MagicMock()
        mock_svc.get_all_settings.return_value = {
            "channel_line_enabled": "true",
            "channel_email_enabled": "true",
        }
        mock_svc_cls.return_value = mock_svc

        mock_noti_instance = MagicMock()
        mock_noti_instance.notify_all = AsyncMock(return_value={})
        mock_noti_cls.create_with_settings.return_value = mock_noti_instance

        await _process_notification(req)

        # Verify: find_user_by_channel_id should NOT be called (direct match)
        mock_svc.find_user_by_channel_id.assert_not_called()

        # Verify: NotificationService created with the original user_id
        mock_noti_cls.create_with_settings.assert_called_once_with(
            settings_service=mock_svc,
            user_id="alice@example.com",
        )
