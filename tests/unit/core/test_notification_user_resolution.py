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
        mock_settings.settings_repo = MagicMock()

        mock_council = MagicMock(spec=CouncilService)
        mock_council.start_session = AsyncMock(
            return_value={"consensus": "SELL immediately — danger detected."}
        )

        sentinel = SentinelService(
            user_id="alice@example.com",
            settings_service=mock_settings,
            council_service=mock_council,
        )

        triggers = [{"id": "vix_spike", "text": "🔴 VIX Spike: 45.0 > 30.0", "level": "CRITICAL"}]

        with patch('src.services.notification_service.NotificationService') as mock_noti_cls, \
             patch('src.services.notification_settings_manager.NotificationSettingsManager') as mock_nsm_cls:
            
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
# Test 2: channel-specific identifiers resolve to/from the internal user
#
# These used to exercise services/notification/src/app/main.py — a standalone
# microservice that was in no compose file and had been superseded by the
# in-process NotificationService. The service is gone; the invariant is not,
# because NotificationService._resolve_channel_id still performs exactly this
# mapping every time an alert is dispatched.
#
# 原本測試的獨立通知微服務已刪除（不在任何 compose 中、早被行程內服務取代），
# 但「內部 user_id ↔ 管道專屬 ID」的對應仍在 _resolve_channel_id 中，故保留驗證。
# ─────────────────────────────────────────────────────

@pytest.mark.anyio
async def test_resolve_channel_id_maps_internal_user_to_channel_identifier():
    """A UUID resolves to that user's LINE identifier for the line adapter."""
    from src.services.notification_service import NotificationService

    uuid = "00000000-0000-4000-a000-000000000001"
    user_repo = MagicMock()
    user_repo.get_identities.return_value = [
        {"provider": "email", "identifier": "owner@example.com", "is_primary": 1},
        {"provider": "line", "identifier": "U1a2b3c4d5e6f", "is_primary": 0},
    ]

    svc = NotificationService(adapters=[], user_repo=user_repo)

    assert await svc._resolve_channel_id(uuid, "line") == "U1a2b3c4d5e6f"
    assert await svc._resolve_channel_id(uuid, "email") == "owner@example.com"
    user_repo.get_identities.assert_called_with(uuid)


@pytest.mark.anyio
async def test_resolve_channel_id_falls_back_to_the_user_id_itself():
    """
    With no matching identity the user_id passes through unchanged, rather than
    resolving to something else or raising — a missing LINE identity must not
    redirect an alert to a different channel's address.
    找不到對應身分時原樣回傳，不得把警示送到別的管道位址。
    """
    from src.services.notification_service import NotificationService

    uuid = "00000000-0000-4000-a000-000000000001"
    user_repo = MagicMock()
    user_repo.get_identities.return_value = [
        {"provider": "email", "identifier": "owner@example.com", "is_primary": 1},
    ]

    svc = NotificationService(adapters=[], user_repo=user_repo)

    assert await svc._resolve_channel_id(uuid, "telegram") == uuid


@pytest.mark.anyio
async def test_broadcast_pseudo_user_is_passed_through():
    """`broadcast` is a sentinel, not a user — it must never hit the repository."""
    from src.services.notification_service import NotificationService

    user_repo = MagicMock()
    svc = NotificationService(adapters=[], user_repo=user_repo)

    assert await svc._resolve_channel_id("broadcast", "line") == "broadcast"
    user_repo.get_identities.assert_not_called()
