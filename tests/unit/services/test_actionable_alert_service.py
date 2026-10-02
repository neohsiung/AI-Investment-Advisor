"""
Unit Tests for Actionable Alert Hub Service (P3)
================================================
Verifies real-time interactive notification dispatch, multi-button payload structure,
callback action execution (close, pause, resume, reset, evict), and Telegram/Slack
interactivity webhook routing.
"""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from httpx import AsyncClient

from src.services.actionable_alert_service import ActionableAlertHubService


@pytest.fixture
def mock_settings_service(monkeypatch):
    mock_ss = MagicMock()
    mock_ss.get_setting.return_value = "true"
    mock_ss.get_all_settings.return_value = {
        "channel_telegram_bot_token": "mock_token_123",
        "channel_telegram_chat_id": "12345678",
    }
    mock_ss.save_setting = MagicMock()
    monkeypatch.setattr("src.services.settings_service.SettingsService", lambda **kw: mock_ss)
    return mock_ss


@pytest.mark.asyncio
async def test_dispatch_support_breakdown_alert():
    hub = ActionableAlertHubService(user_id="test_user_p3")

    with patch.object(hub, "_get_notification_service") as mock_get_noti:
        mock_noti = MagicMock()
        mock_noti.notify_all = AsyncMock(return_value={"TelegramAdapter": True})
        mock_get_noti.return_value = mock_noti

        res = await hub.dispatch_support_breakdown_alert(
            ticker="NVDA",
            current_price=110.0,
            support_price=118.5,
            breakdown_pct=-7.17,
            unrealized_pnl_pct=-3.5,
            position_value=2500.0,
        )

        assert res == {"TelegramAdapter": True}
        mock_noti.notify_all.assert_called_once()
        _, kwargs = mock_noti.notify_all.call_args
        assert "NVDA" in kwargs["title"]
        assert "跌破主力支撐" in kwargs["title"]
        assert "$110.00" in kwargs["content"]
        assert "$118.50" in kwargs["content"]
        actions = kwargs["actions"]
        assert len(actions) == 3
        action_names = [a["key"] for a in actions]
        assert "close_pos" in action_names
        assert "pause_trading" in action_names
        assert "dismiss" in action_names
        assert "ticker=NVDA" in actions[0]["data"]


@pytest.mark.asyncio
async def test_dispatch_protection_breached_alert():
    hub = ActionableAlertHubService(user_id="test_user_p3")

    with patch.object(hub, "_get_notification_service") as mock_get_noti:
        mock_noti = MagicMock()
        mock_noti.notify_all = AsyncMock(return_value={"TelegramAdapter": True})
        mock_get_noti.return_value = mock_noti

        res = await hub.dispatch_protection_breached_alert(
            rule_name="連續虧損鎖定",
            reason="last 3 resolved BUY decisions all lost alpha",
            ticker="TSLA",
            consecutive_losses=3,
        )

        assert res == {"TelegramAdapter": True}
        _, kwargs = mock_noti.notify_all.call_args
        assert "風控保護機制觸發" in kwargs["title"]
        assert "TSLA" in kwargs["title"]
        assert "連續虧損鎖定" in kwargs["content"]
        actions = kwargs["actions"]
        assert any(a["key"] == "reset_protection" for a in actions)


@pytest.mark.asyncio
async def test_dispatch_shadow_graduation_alert_graduated():
    hub = ActionableAlertHubService(user_id="test_user_p3")

    with patch.object(hub, "_get_notification_service") as mock_get_noti:
        mock_noti = MagicMock()
        mock_noti.notify_all = AsyncMock(return_value={"TelegramAdapter": True})
        mock_get_noti.return_value = mock_noti

        await hub.dispatch_shadow_graduation_alert(
            ticker="MSFT",
            graduated=True,
            metrics={"final_price": 450.0},
            eval_days=10,
            unrealized_pnl_pct=4.25,
            max_drawdown_pct=2.1,
            support_breached=False,
        )

        _, kwargs = mock_noti.notify_all.call_args
        assert "考核合格" in kwargs["title"]
        assert "晉升實盤" in kwargs["title"]
        assert "+4.25%" in kwargs["content"]
        actions = kwargs["actions"]
        assert any(a["key"] == "view_universe" for a in actions)


@pytest.mark.asyncio
async def test_dispatch_shadow_graduation_alert_failed():
    hub = ActionableAlertHubService(user_id="test_user_p3")

    with patch.object(hub, "_get_notification_service") as mock_get_noti:
        mock_noti = MagicMock()
        mock_noti.notify_all = AsyncMock(return_value={"TelegramAdapter": True})
        mock_get_noti.return_value = mock_noti

        await hub.dispatch_shadow_graduation_alert(
            ticker="SPEC",
            graduated=False,
            metrics={"final_price": 9.5},
            eval_days=8,
            unrealized_pnl_pct=-6.8,
            max_drawdown_pct=8.5,
            support_breached=True,
        )

        _, kwargs = mock_noti.notify_all.call_args
        assert "未通過" in kwargs["title"]
        assert "淘汰降級" in kwargs["title"]
        actions = kwargs["actions"]
        assert any(a["key"] == "confirm_evict" for a in actions)


@pytest.mark.asyncio
async def test_dispatch_large_slippage_alert():
    hub = ActionableAlertHubService(user_id="test_user_p3")

    with patch.object(hub, "_get_notification_service") as mock_get_noti:
        mock_noti = MagicMock()
        mock_noti.notify_all = AsyncMock(return_value={"TelegramAdapter": True})
        mock_get_noti.return_value = mock_noti

        await hub.dispatch_large_slippage_alert(
            ticker="AMZN",
            expected_price=185.0,
            executed_price=187.2,
            slippage_pct=1.19,
            action="BUY",
        )

        _, kwargs = mock_noti.notify_all.call_args
        assert "執行滑價異常警告" in kwargs["title"]
        assert "1.19%" in kwargs["content"]


@pytest.mark.asyncio
async def test_execute_action_pause_and_resume(mock_settings_service):
    hub = ActionableAlertHubService(user_id="test_user_p3")

    res_pause = await hub.execute_action("pause_trading")
    assert res_pause["ok"] is True
    assert "已成功暫停" in res_pause["message"]
    mock_settings_service.save_setting.assert_called_with("ai_trading_enabled", "false")

    res_resume = await hub.execute_action("resume_trading")
    assert res_resume["ok"] is True
    assert "已成功恢復" in res_resume["message"]
    mock_settings_service.save_setting.assert_called_with("ai_trading_enabled", "true")


@pytest.mark.asyncio
async def test_execute_action_close_pos():
    hub = ActionableAlertHubService(user_id="test_user_p3")

    with patch("src.services.etoro_service.EtoroService") as MockEtoro:
        mock_instance = MagicMock()
        mock_instance.get_portfolio.return_value = {
            "positions": [
                {"id": "pos_999", "ticker": "AMD", "value": 1500.0}
            ]
        }
        mock_instance.close_position = MagicMock()
        MockEtoro.return_value = mock_instance

        res = await hub.execute_action("close_pos", {"ticker": "AMD"})
        assert res["ok"] is True
        assert "AMD" in res["message"]
        mock_instance.close_position.assert_called_once_with(position_id="pos_999")


@pytest.mark.asyncio
async def test_execute_action_confirm_eviction():
    hub = ActionableAlertHubService(user_id="test_user_p3")

    with patch("src.repositories.ticker_universe_repository.TickerUniverseRepository") as MockRepo:
        mock_repo_inst = MagicMock()
        MockRepo.return_value = mock_repo_inst

        res = await hub.execute_action("confirm_eviction", {"ticker": "JUNK"})
        assert res["ok"] is True
        assert "JUNK" in res["message"]
        mock_repo_inst.upsert.assert_called_once_with("test_user_p3", "JUNK", status="removed")
        mock_repo_inst.add_log.assert_called_once()


@pytest.mark.asyncio
async def test_execute_action_reset_and_dismiss(mock_settings_service):
    hub = ActionableAlertHubService(user_id="test_user_p3")

    res_reset = await hub.execute_action("reset_protection")
    assert res_reset["ok"] is True
    assert "已手動重設" in res_reset["message"]

    res_dismiss = await hub.execute_action("dismiss")
    assert res_dismiss["ok"] is True
    assert "已確認知悉" in res_dismiss["message"]


def _tg_req(payload):
    req = MagicMock()
    req.json = AsyncMock(return_value=payload)
    return req


def _slack_req(body_bytes: bytes, headers: dict = None):
    req = MagicMock()
    req.body = AsyncMock(return_value=body_bytes)
    req.headers = headers or {}
    return req


@pytest.mark.asyncio
async def test_telegram_webhook_actionable_callback():
    from src.services import webhook_service as ws

    payload = {
        "update_id": 999123,
        "callback_query": {
            "id": "query_test_123",
            "from": {"id": 12345678, "username": "trader"},
            "data": "action=pause_trading",
            "message": {
                "message_id": 55,
                "chat": {"id": 12345678, "type": "private"},
            }
        }
    }

    with patch("src.services.settings_service.SettingsService") as MockSS, \
         patch("httpx.AsyncClient.post") as mock_http_post, \
         patch("src.services.actionable_alert_service.ActionableAlertHubService.execute_action", new_callable=AsyncMock) as mock_exec:

        mock_ss_inst = MagicMock()
        mock_ss_inst.find_user_by_channel_id.return_value = "user_p3"
        mock_ss_inst.get_setting.return_value = "mock_token"
        MockSS.return_value = mock_ss_inst

        mock_exec.return_value = {"ok": True, "message": "⏸️ 已成功暫停 AI 自動交易。"}

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"ok": True}
        mock_http_post.return_value = mock_resp

        req = _tg_req(payload)
        res = await ws.telegram_bot_webhook(req)
        assert res == {"ok": True}
        mock_exec.assert_called_once_with("pause_trading", {"action": "pause_trading"})


@pytest.mark.asyncio
async def test_telegram_webhook_support_and_shadow_commands():
    from src.services import webhook_service as ws

    with patch("src.services.settings_service.SettingsService") as MockSS, \
         patch("src.services.smart_money_support_service.SmartMoneySupportService") as MockSM, \
         patch("src.services.shadow_ledger_service.ShadowLedgerService") as MockShadow, \
         patch("httpx.AsyncClient.post") as mock_http_post:

        mock_ss_inst = MagicMock()
        mock_ss_inst.find_user_by_channel_id.return_value = "user_p3"
        mock_ss_inst.get_setting.return_value = "mock_token"
        MockSS.return_value = mock_ss_inst

        # Mock SmartMoney
        mock_sm_inst = MagicMock()
        mock_res = MagicMock()
        mock_res.current_price = 150.0
        mock_res.key_support_price = 145.0
        mock_res.recommended_stop_loss = 143.8
        mock_res.anchored_vwap = 144.5
        mock_res.point_of_control = 145.0
        mock_res.value_area_high = 152.0
        mock_res.value_area_low = 142.0
        mock_res.is_bullish_support = True
        mock_res.notes = "Strong institutional floor"
        mock_sm_inst.calculate_institutional_support = AsyncMock(return_value=mock_res)
        MockSM.return_value = mock_sm_inst

        # Mock Shadow
        mock_shadow_inst = MagicMock()
        mock_shadow_inst.repo.list_positions.return_value = [
            {
                "ticker": "AAPL",
                "evaluation_days": 8,
                "unrealized_pnl_pct": 3.2,
                "max_drawdown_pct": 1.5,
                "support_breached": False,
            }
        ]
        MockShadow.return_value = mock_shadow_inst

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"ok": True}
        mock_http_post.return_value = mock_resp

        # Test /support AAPL
        req1 = _tg_req({
            "update_id": 999124,
            "message": {
                "message_id": 56,
                "chat": {"id": 12345678, "type": "private"},
                "text": "/support AAPL"
            }
        })
        res1 = await ws.telegram_bot_webhook(req1)
        assert res1 == {"ok": True}

        # Test /shadow
        req2 = _tg_req({
            "update_id": 999125,
            "message": {
                "message_id": 57,
                "chat": {"id": 12345678, "type": "private"},
                "text": "/shadow"
            }
        })
        res2 = await ws.telegram_bot_webhook(req2)
        assert res2 == {"ok": True}


@pytest.mark.asyncio
async def test_slack_interactivity_webhook():
    from src.services import webhook_service as ws

    slack_payload = {
        "type": "block_actions",
        "user": {"id": "U123456", "name": "slack_trader"},
        "actions": [
            {
                "action_id": "pause_trading",
                "value": "action=pause_trading",
                "type": "button",
            }
        ]
    }

    form_body = f"payload={json.dumps(slack_payload)}"

    with patch("src.infrastructure.channels.slack_adapter.SlackAdapter.verify_signature", return_value=True), \
         patch("src.services.actionable_alert_service.ActionableAlertHubService.execute_action", new_callable=AsyncMock) as mock_exec:

        mock_exec.return_value = {"ok": True, "message": "⏸️ 已成功暫停 AI 自動交易。"}

        req = _slack_req(
            body_bytes=form_body.encode("utf-8"),
            headers={"content-type": "application/x-www-form-urlencoded"},
        )
        res = await ws.slack_interactivity_webhook(req)
        assert res["ok"] is True or "response_type" in res
        mock_exec.assert_called_once_with("pause_trading", {"action": "pause_trading"})
