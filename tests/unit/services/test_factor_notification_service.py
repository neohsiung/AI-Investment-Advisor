"""
Unit Tests for FactorNotificationService (Option B: Multi-Channel Alerts)
========================================================================
Verifies:
  1. Factor promotion alerts (manual approval & 14-day canary graduation).
  2. Circuit breaker alerts (automated -5% loss & manual operator kill-switch).
  3. Live factor-influenced order decision alerts.
  4. Constraint #0 compliance (fail-safe error handling and logging).
  5. NotificationSettingsManager recognition of Slack, LINE, and Discord channels.
"""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.services.factor_notification_service import (
    FactorNotificationService,
    factor_notification_service,
)
from src.services.notification_settings_manager import (
    NotificationChannel,
    NotificationSettingsManager,
)


@pytest.fixture
def mock_settings_service():
    svc = MagicMock()
    svc.settings_repo = MagicMock()
    svc.settings_repo.get.return_value = "web,telegram"
    return svc


@pytest.fixture
def mock_notif_service():
    mock_svc = MagicMock()
    mock_svc.notify_all = AsyncMock(return_value={"web": True, "telegram": True})
    return mock_svc


@pytest.mark.asyncio
async def test_notify_factor_promoted_manual(mock_settings_service, mock_notif_service):
    service = FactorNotificationService(settings_service=mock_settings_service)

    with patch.object(service, "_get_notification_service", return_value=mock_notif_service), \
         patch.object(service, "_get_active_channels", return_value=["telegram", "web"]):
        
        result = await service.notify_factor_promoted(
            artifact_name="volatility_pivot_mean_reversion",
            regime="VOLATILITY_PIVOT",
            user_id="00000000-0000-4000-a000-000000000001",
            metrics={"sharpe_ratio": 1.45, "max_drawdown_pct": 12.3, "net_profit_pct": 28.5},
            approval_type="manual",
        )

        assert result["success"] is True
        assert result["channels"] == ["telegram", "web"]
        mock_notif_service.notify_all.assert_called_once()
        call_kwargs = mock_notif_service.notify_all.call_args.kwargs
        assert "核發實盤執照" in call_kwargs["title"]
        assert "volatility_pivot_mean_reversion" in call_kwargs["content"]
        assert "操作者人工審定核發" in call_kwargs["content"]
        assert "1.45" in call_kwargs["content"]
        assert "12.3%" in call_kwargs["content"]
        assert "28.5%" in call_kwargs["content"]
        assert call_kwargs["category"] == "system"


@pytest.mark.asyncio
async def test_notify_factor_promoted_canary_graduation(mock_settings_service, mock_notif_service):
    service = FactorNotificationService(settings_service=mock_settings_service)

    with patch.object(service, "_get_notification_service", return_value=mock_notif_service), \
         patch.object(service, "_get_active_channels", return_value=["slack"]):
        
        result = await service.notify_factor_promoted(
            artifact_name="trend_acceleration_breakout",
            regime="TREND_ACCELERATION",
            user_id="00000000-0000-4000-a000-000000000001",
            metrics={"sharpe_ratio": 1.82, "max_drawdown_pct": 8.5, "net_profit_pct": 42.1},
            approval_type="canary_graduation",
        )

        assert result["success"] is True
        call_kwargs = mock_notif_service.notify_all.call_args.kwargs
        assert "14 日金絲雀灰度考核通過" in call_kwargs["content"]
        assert "trend_acceleration_breakout" in call_kwargs["content"]


@pytest.mark.asyncio
async def test_notify_circuit_breaker_tripped_automated(mock_settings_service, mock_notif_service):
    service = FactorNotificationService(settings_service=mock_settings_service)

    with patch.object(service, "_get_notification_service", return_value=mock_notif_service), \
         patch.object(service, "_get_active_channels", return_value=["telegram"]):
        
        result = await service.notify_circuit_breaker_tripped(
            artifact_name="fragile_liquidity_factor",
            reason="Single-day shadow loss -5.8% exceeded threshold",
            user_id="00000000-0000-4000-a000-000000000001",
            daily_pnl_pct=-5.8,
        )

        assert result["success"] is True
        mock_notif_service.notify_all.assert_called_once()
        call_kwargs = mock_notif_service.notify_all.call_args.kwargs
        assert "🚨 [安全熔斷]" in call_kwargs["title"]
        assert "fragile_liquidity_factor" in call_kwargs["content"]
        assert "-5.80%" in call_kwargs["content"]
        assert "REJECTED" in call_kwargs["content"]
        assert call_kwargs["category"] == "sentinel"


@pytest.mark.asyncio
async def test_notify_circuit_breaker_tripped_manual_kill(mock_settings_service, mock_notif_service):
    service = FactorNotificationService(settings_service=mock_settings_service)

    with patch.object(service, "_get_notification_service", return_value=mock_notif_service), \
         patch.object(service, "_get_active_channels", return_value=["web"]):
        
        result = await service.notify_circuit_breaker_tripped(
            artifact_name="liquidity_shock_factor",
            reason="Operator Emergency Kill-Switch (人工緊急下線)",
            user_id="00000000-0000-4000-a000-000000000001",
        )

        assert result["success"] is True
        call_kwargs = mock_notif_service.notify_all.call_args.kwargs
        assert "Operator Emergency Kill-Switch" in call_kwargs["content"]
        assert "KILLED" in call_kwargs["content"]


@pytest.mark.asyncio
async def test_notify_factor_order_decision(mock_settings_service, mock_notif_service):
    service = FactorNotificationService(settings_service=mock_settings_service)

    with patch.object(service, "_get_notification_service", return_value=mock_notif_service), \
         patch.object(service, "_get_active_channels", return_value=["telegram", "slack"]):
        
        result = await service.notify_factor_order_decision(
            ticker="NVDA",
            action="BUY",
            amount_usd=25.0,
            composite_score=6.74,
            factor_name="liquidity_shock_mean_reversion_score",
            factor_confidence=9.99,
            user_id="00000000-0000-4000-a000-000000000001",
        )

        assert result["success"] is True
        mock_notif_service.notify_all.assert_called_once()
        call_kwargs = mock_notif_service.notify_all.call_args.kwargs
        assert "NVDA" in call_kwargs["title"]
        assert "BUY" in call_kwargs["content"]
        assert "$25.00" in call_kwargs["content"]
        assert "6.74 / 10.0" in call_kwargs["content"]
        assert "liquidity_shock_mean_reversion_score" in call_kwargs["content"]
        assert "9.99 / 10.0" in call_kwargs["content"]
        assert "15%" in call_kwargs["content"]
        assert call_kwargs["category"] == "trading"


@pytest.mark.asyncio
async def test_factor_notification_graceful_error_handling(mock_settings_service):
    """
    Constraint #0: Notification dispatch failures must be logged at WARNING/ERROR
    and must not raise unhandled exceptions.
    """
    failing_notif_service = MagicMock()
    failing_notif_service.notify_all = AsyncMock(side_effect=RuntimeError("Channel network timeout"))

    service = FactorNotificationService(settings_service=mock_settings_service)

    with patch.object(service, "_get_notification_service", return_value=failing_notif_service):
        result = await service.notify_factor_promoted(
            artifact_name="test_factor",
            regime="NORMAL",
            user_id="00000000-0000-4000-a000-000000000001",
        )
        assert result["success"] is False
        assert "Channel network timeout" in result["error"]

        result_kill = await service.notify_circuit_breaker_tripped(
            artifact_name="test_factor",
            reason="manual kill",
            user_id="00000000-0000-4000-a000-000000000001",
        )
        assert result_kill["success"] is False
        assert "Channel network timeout" in result_kill["error"]


def test_notification_settings_manager_supports_slack_line_discord():
    """
    Verify NotificationChannel enum and active channel detection supports SLACK, LINE, and DISCORD.
    """
    assert NotificationChannel.SLACK.value == "slack"
    assert NotificationChannel.LINE.value == "line"
    assert NotificationChannel.DISCORD.value == "discord"

    mock_repo = MagicMock()
    mock_repo.get.side_effect = lambda user_id, key, default=None: {
        "notification_channels": "slack,line,discord,email",
        "channel_slack_channel_id": "C12345678",
        "channel_line_user_id": "U12345678",
        "channel_discord_webhook_url": "https://discord.com/api/webhooks/123",
    }.get(key, default)

    nsm = NotificationSettingsManager(settings_repo=mock_repo, user_id="00000000-0000-4000-a000-000000000001")
    active = nsm.get_active_notification_channels()

    assert "slack" in active
    assert "line" in active
    assert "discord" in active
    assert "email" in active
