"""
Unit tests for the Telegram bot webhook endpoint.
Telegram Bot Webhook 端點單元測試。

Two things make this endpoint worth covering carefully:

1. It is an unauthenticated public surface. Telegram is told to POST here, and
   the only gate is that `find_user_by_channel_id` resolves the chat_id to a
   user — so every early-return path (bad JSON, no chat_id, unknown chat) is a
   security boundary, not just an edge case.
2. `/pause` and `/resume` write `ai_trading_enabled`, i.e. the kill switch for a
   live trading account, and `/backtest` writes to the database. A command
   dispatching to the wrong closure is a real incident.

Testing note: every command body is an inner `async def` handed to
`asyncio.create_task`. Under fastapi.testclient the response returns before
those tasks run, so their bodies never execute and never get covered. These
tests therefore await the endpoint coroutine directly and then yield to the
loop so the scheduled tasks actually run.

測試要點：所有指令主體都是丟給 asyncio.create_task 的內層 async def，用
TestClient 會在它們執行前就拿到回應，等於完全沒測到。因此這裡直接 await
端點協程，再讓出控制權讓排程的 task 真的跑起來。
"""
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.services import webhook_service as ws

CHAT_ID = "987654321"
USER_ID = "11111111-2222-4333-8444-555555555555"


def _request(payload, raises=False):
    """Minimal stand-in for fastapi.Request — only .json() is used."""
    req = MagicMock()
    if raises:
        req.json = AsyncMock(side_effect=ValueError("not json"))
    else:
        req.json = AsyncMock(return_value=payload)
    return req


def _message(text):
    return {"message": {"chat": {"id": CHAT_ID}, "text": text}}


async def _drain():
    """Let create_task'd closures run to completion."""
    for _ in range(6):
        await asyncio.sleep(0)


class _Harness:
    """
    Patches user resolution and the reply transport, and records replies.

    `_reply` builds its own SettingsService and posts through httpx; patching
    SettingsService at the source module covers both that and the resolution
    lookup, and patching httpx.AsyncClient keeps the test off the network.
    """

    def __init__(self, bot_token="tok"):
        self.replies = []
        self.bot_token = bot_token
        self._patches = []

    def __enter__(self):
        settings = MagicMock()
        settings.find_user_by_channel_id.return_value = USER_ID
        settings.get_setting.side_effect = lambda key, default=None: (
            self.bot_token if key == "channel_telegram_bot_token" else default
        )
        self.settings = settings

        cls = patch("src.services.settings_service.SettingsService",
                    return_value=settings)
        self._patches.append(cls)
        cls.start()

        client = MagicMock()
        client.__aenter__ = AsyncMock(return_value=client)
        client.__aexit__ = AsyncMock(return_value=False)

        async def _post(url, json=None, **kw):
            self.replies.append(json["text"])
            return MagicMock(status_code=200)

        client.post = AsyncMock(side_effect=_post)
        httpx_patch = patch("httpx.AsyncClient", return_value=client)
        self._patches.append(httpx_patch)
        httpx_patch.start()
        return self

    def __exit__(self, *exc):
        for p in reversed(self._patches):
            p.stop()
        return False

    @property
    def text(self):
        return "\n".join(self.replies)


class TestPayloadParsing:
    async def test_malformed_json_returns_ok(self):
        """Telegram retries on non-200, so a bad body must still answer 200."""
        assert await ws.telegram_bot_webhook(_request(None, raises=True)) == {"ok": True}

    async def test_missing_chat_id_returns_ok(self):
        assert await ws.telegram_bot_webhook(_request({})) == {"ok": True}

    async def test_edited_message_is_handled_like_a_message(self):
        with _Harness() as h:
            await ws.telegram_bot_webhook(_request(
                {"edited_message": {"chat": {"id": CHAT_ID}, "text": "/start"}}))
            await _drain()
        assert "Investment Advisor Bot" in h.text

    async def test_message_without_text_is_tolerated(self):
        with _Harness() as h:
            result = await ws.telegram_bot_webhook(
                _request({"message": {"chat": {"id": CHAT_ID}}}))
            await _drain()
        assert result == {"ok": True}
        assert h.replies == []


class TestUserResolution:
    async def test_unknown_chat_id_is_ignored(self):
        settings = MagicMock()
        settings.find_user_by_channel_id.return_value = None
        with patch("src.services.settings_service.SettingsService", return_value=settings):
            assert await ws.telegram_bot_webhook(_request(_message("/status"))) == {"ok": True}

    async def test_resolution_failure_is_ignored(self):
        """A DB outage must not turn into a 500 that Telegram will retry forever."""
        with patch("src.services.settings_service.SettingsService",
                   side_effect=RuntimeError("db down")):
            assert await ws.telegram_bot_webhook(_request(_message("/status"))) == {"ok": True}


class TestReplyTransport:
    async def test_no_bot_token_sends_nothing(self):
        with _Harness(bot_token="") as h:
            await ws.telegram_bot_webhook(_request(_message("/start")))
            await _drain()
        assert h.replies == []

    async def test_transport_failure_is_swallowed(self):
        """A failed reply must not escape the endpoint."""
        settings = MagicMock()
        settings.find_user_by_channel_id.return_value = USER_ID
        settings.get_setting.return_value = "tok"
        with patch("src.services.settings_service.SettingsService", return_value=settings), \
             patch("httpx.AsyncClient", side_effect=RuntimeError("network down")):
            result = await ws.telegram_bot_webhook(_request(_message("/start")))
            await _drain()
        assert result == {"ok": True}


class TestCallbackQuery:
    async def test_callback_registers_interaction_handler(self):
        adapter = MagicMock()
        adapter.handle_webhook = AsyncMock()
        payload = {"callback_query": {"message": {"chat": {"id": CHAT_ID}}, "data": "approve:42"}}

        with _Harness(), \
             patch("src.infrastructure.channels.telegram_adapter.TelegramAdapter",
                   return_value=adapter), \
             patch("src.services.interaction_service.InteractionService") as MockIS:
            result = await ws.telegram_bot_webhook(_request(payload))
            await _drain()

        assert result == {"ok": True}
        adapter.register_callback.assert_called_once_with(
            MockIS.return_value.handle_response)
        adapter.handle_webhook.assert_awaited_once_with(payload)

    async def test_callback_failure_is_swallowed(self):
        payload = {"callback_query": {"message": {"chat": {"id": CHAT_ID}}, "data": "x"}}
        with _Harness(), \
             patch("src.infrastructure.channels.telegram_adapter.TelegramAdapter",
                   side_effect=RuntimeError("adapter boom")):
            assert await ws.telegram_bot_webhook(_request(payload)) == {"ok": True}


class TestHelpCommand:
    @pytest.mark.parametrize("cmd", ["/start", "/help"])
    async def test_help_lists_every_command(self, cmd):
        with _Harness() as h:
            await ws.telegram_bot_webhook(_request(_message(cmd)))
            await _drain()
        for expected in ("/report", "/status", "/sentinel", "/portfolio",
                         "/backtest", "/health", "/pause", "/resume"):
            assert expected in h.text

    async def test_command_matching_is_case_insensitive(self):
        with _Harness() as h:
            await ws.telegram_bot_webhook(_request(_message("/START")))
            await _drain()
        assert "Investment Advisor Bot" in h.text


class TestStatusAndPortfolio:
    _PORTFOLIO = {
        "positions": [
            {"ticker": "AAPL", "value": 5000, "pnl_pct": 12.5},
            {"ticker": "MSFT", "value": 3000, "pnl_pct": -4.0},
        ],
        "cash_available": 2000,
        "net_liquidation_value": 10000,
    }

    async def test_status_reports_cash_ratio_and_positions(self):
        etoro = MagicMock()
        etoro.get_portfolio.return_value = self._PORTFOLIO
        with _Harness() as h, \
             patch("src.services.etoro_service.EtoroService", return_value=etoro):
            await ws.telegram_bot_webhook(_request(_message("/status")))
            await _drain()
        assert "2 持倉" in h.text
        assert "$2,000 (20.0%)" in h.text
        assert "AAPL" in h.text and "MSFT" in h.text

    async def test_status_handles_zero_nlv_without_dividing_by_zero(self):
        etoro = MagicMock()
        etoro.get_portfolio.return_value = {"positions": [], "cash_available": 0,
                                            "net_liquidation_value": 0}
        with _Harness() as h, \
             patch("src.services.etoro_service.EtoroService", return_value=etoro):
            await ws.telegram_bot_webhook(_request(_message("/status")))
            await _drain()
        assert "(0.0%)" in h.text

    async def test_status_broker_failure_reports_error(self):
        with _Harness() as h, \
             patch("src.services.etoro_service.EtoroService",
                   side_effect=RuntimeError("broker down")):
            await ws.telegram_bot_webhook(_request(_message("/status")))
            await _drain()
        assert "❌ 無法取得帳戶狀態" in h.text

    async def test_portfolio_formats_gain_and_loss_differently(self):
        etoro = MagicMock()
        etoro.get_portfolio.return_value = self._PORTFOLIO
        with _Harness() as h, \
             patch("src.services.etoro_service.EtoroService", return_value=etoro):
            await ws.telegram_bot_webhook(_request(_message("/portfolio")))
            await _drain()
        assert "+12.5%" in h.text
        assert "-4.0%" in h.text

    async def test_portfolio_failure_reports_error(self):
        with _Harness() as h, \
             patch("src.services.etoro_service.EtoroService",
                   side_effect=RuntimeError("nope")):
            await ws.telegram_bot_webhook(_request(_message("/portfolio")))
            await _drain()
        assert "❌ 無法取得持倉" in h.text


class TestSentinelAndReport:
    async def test_sentinel_runs_a_tick(self):
        sentinel = MagicMock()
        sentinel.process_tick = AsyncMock()
        with _Harness() as h, \
             patch.object(ws, "SentinelService", return_value=sentinel):
            await ws.telegram_bot_webhook(_request(_message("/sentinel")))
            await _drain()
        sentinel.process_tick.assert_awaited_once()
        assert "✅ Sentinel 掃描完成" in h.text

    async def test_sentinel_failure_reports_error(self):
        with _Harness() as h, \
             patch.object(ws, "SentinelService", side_effect=RuntimeError("tick boom")):
            await ws.telegram_bot_webhook(_request(_message("/sentinel")))
            await _drain()
        assert "❌ Sentinel 執行失敗" in h.text

    async def test_report_starts_the_daily_workflow(self):
        wf = MagicMock()
        wf.run = AsyncMock()
        with _Harness() as h, \
             patch("src.services.workflow_service.DailyWorkflow", return_value=wf):
            await ws.telegram_bot_webhook(_request(_message("/report")))
            await _drain()
        assert "✅ 每日報告已開始生成" in h.text

    async def test_report_failure_reports_error(self):
        with _Harness() as h, \
             patch("src.services.workflow_service.DailyWorkflow",
                   side_effect=RuntimeError("wf boom")):
            await ws.telegram_bot_webhook(_request(_message("/report")))
            await _drain()
        assert "❌ 報告生成失敗" in h.text


class TestBacktestCommand:
    _OHLCV = {"close": [100.0 + i for i in range(180)]}

    async def test_missing_ticker_shows_usage(self):
        with _Harness() as h:
            await ws.telegram_bot_webhook(_request(_message("/backtest")))
            await _drain()
        assert "用法: /backtest" in h.text

    async def test_insufficient_history_is_reported(self):
        market = MagicMock()
        market.get_ohlcv.return_value = {"close": [1.0, 2.0]}
        with _Harness() as h, \
             patch("src.services.market_data_service.MarketDataService", return_value=market):
            await ws.telegram_bot_webhook(_request(_message("/backtest aapl")))
            await _drain()
        assert "歷史數據不足" in h.text

    async def test_successful_backtest_persists_and_reports_metrics(self):
        market = MagicMock()
        market.get_ohlcv.return_value = self._OHLCV
        result = MagicMock(final_cash=123456.0, trades=[], equity_curve=[1.0], dates=["d"])
        result.metrics = {"sharpe": 1.5, "sortino": 2.0, "cagr_pct": 12.0,
                          "max_drawdown_pct": -5.0, "win_rate_pct": 60.0,
                          "total_trades": 7}
        engine = MagicMock()
        engine.run.return_value = result
        repo = MagicMock()

        with _Harness() as h, \
             patch("src.services.market_data_service.MarketDataService", return_value=market), \
             patch("src.services.portfolio_backtest_engine.PortfolioBacktestEngine",
                   return_value=engine), \
             patch("src.services.portfolio_backtest_engine.simple_ma_crossover_signal"), \
             patch("src.repositories.backtest_repository.AlchemyBacktestRepository",
                   return_value=repo):
            await ws.telegram_bot_webhook(_request(_message("/backtest aapl")))
            await _drain()

        # Ticker is upper-cased before it reaches the engine and the repository.
        assert repo.save_run.call_args.kwargs["ticker"] == "AAPL"
        assert repo.save_run.call_args.kwargs["strategy_name"] == "ma_crossover_10_30"
        assert "AAPL 回測結果" in h.text
        assert "$123,456" in h.text
        assert "1.50" in h.text and "60.00%" in h.text

    async def test_missing_metrics_render_as_dash(self):
        market = MagicMock()
        market.get_ohlcv.return_value = self._OHLCV
        result = MagicMock(final_cash=100.0, trades=[], equity_curve=[], dates=[])
        result.metrics = {"total_trades": 0}
        engine = MagicMock()
        engine.run.return_value = result

        with _Harness() as h, \
             patch("src.services.market_data_service.MarketDataService", return_value=market), \
             patch("src.services.portfolio_backtest_engine.PortfolioBacktestEngine",
                   return_value=engine), \
             patch("src.services.portfolio_backtest_engine.simple_ma_crossover_signal"), \
             patch("src.repositories.backtest_repository.AlchemyBacktestRepository"):
            await ws.telegram_bot_webhook(_request(_message("/backtest xyz")))
            await _drain()
        assert "—" in h.text

    async def test_engine_failure_reports_error(self):
        with _Harness() as h, \
             patch("src.services.market_data_service.MarketDataService",
                   side_effect=RuntimeError("no data")):
            await ws.telegram_bot_webhook(_request(_message("/backtest aapl")))
            await _drain()
        assert "❌ 回測失敗" in h.text


class TestHealthCommand:
    async def test_reports_enabled_and_no_halt(self):
        protections = MagicMock()
        protections.check.return_value = None
        with _Harness() as h, \
             patch("src.services.trading_protections_service.TradingProtectionsService",
                   return_value=protections):
            h.settings.get_setting.side_effect = lambda key, default=None: {
                "channel_telegram_bot_token": "tok", "ai_trading_enabled": "true",
            }.get(key, default)
            await ws.telegram_bot_webhook(_request(_message("/health")))
            await _drain()
        assert "✅ 啟用" in h.text
        assert "✅ 正常，無停機觸發" in h.text

    async def test_reports_paused_and_active_halt(self):
        protections = MagicMock()
        protections.check.return_value = "Global drawdown halt"
        with _Harness() as h, \
             patch("src.services.trading_protections_service.TradingProtectionsService",
                   return_value=protections):
            h.settings.get_setting.side_effect = lambda key, default=None: {
                "channel_telegram_bot_token": "tok", "ai_trading_enabled": "false",
            }.get(key, default)
            await ws.telegram_bot_webhook(_request(_message("/health")))
            await _drain()
        assert "⏸️ 已暫停" in h.text
        assert "Global drawdown halt" in h.text

    async def test_failure_reports_error(self):
        with _Harness() as h, \
             patch("src.services.trading_protections_service.TradingProtectionsService",
                   side_effect=RuntimeError("check boom")):
            await ws.telegram_bot_webhook(_request(_message("/health")))
            await _drain()
        assert "❌ 健康檢查失敗" in h.text


class TestKillSwitchCommands:
    """
    /pause and /resume drive ai_trading_enabled on a live account. The value
    must be the STRING "false"/"true": settings.value is a JSON column, and a
    JSON boolean written here is what broke RiskManager on 2026-08-02.
    這兩個指令操作真實帳戶的交易總開關，且必須寫入字串而非 JSON boolean。
    """

    async def test_pause_writes_string_false(self):
        with _Harness() as h:
            await ws.telegram_bot_webhook(_request(_message("/pause")))
            await _drain()
        h.settings.save_setting.assert_called_once_with("ai_trading_enabled", "false")
        assert isinstance(h.settings.save_setting.call_args.args[1], str)
        assert "⏸️ AI 自動交易已暫停" in h.text

    async def test_resume_writes_string_true(self):
        with _Harness() as h:
            await ws.telegram_bot_webhook(_request(_message("/resume")))
            await _drain()
        h.settings.save_setting.assert_called_once_with("ai_trading_enabled", "true")
        assert isinstance(h.settings.save_setting.call_args.args[1], str)
        assert "▶️ AI 自動交易已恢復" in h.text

    @pytest.mark.parametrize("cmd,expected", [("/pause", "❌ 暫停失敗"),
                                              ("/resume", "❌ 恢復失敗")])
    async def test_write_failure_is_reported(self, cmd, expected):
        with _Harness() as h:
            h.settings.save_setting.side_effect = RuntimeError("db down")
            await ws.telegram_bot_webhook(_request(_message(cmd)))
            await _drain()
        assert expected in h.text


class TestFreeformText:
    async def test_plain_text_goes_to_the_conversation_agent(self):
        agent = MagicMock()
        agent.chat = AsyncMock(return_value={"response": "42"})
        with _Harness() as h, \
             patch("src.agents.conversation_agent.ConversationAgent", return_value=agent):
            await ws.telegram_bot_webhook(_request(_message("what is my exposure?")))
            await _drain()
        agent.chat.assert_awaited_once_with("what is my exposure?")
        assert "🤖 42" in h.text

    async def test_agent_without_response_key_uses_fallback(self):
        agent = MagicMock()
        agent.chat = AsyncMock(return_value={})
        with _Harness() as h, \
             patch("src.agents.conversation_agent.ConversationAgent", return_value=agent):
            await ws.telegram_bot_webhook(_request(_message("hello")))
            await _drain()
        assert "抱歉，我暫時無法回答這個問題" in h.text

    async def test_agent_failure_reports_error(self):
        with _Harness() as h, \
             patch("src.agents.conversation_agent.ConversationAgent",
                   side_effect=RuntimeError("agent boom")):
            await ws.telegram_bot_webhook(_request(_message("hello")))
            await _drain()
        assert "❌ 無法處理查詢" in h.text

    async def test_unknown_slash_command_is_silently_ignored(self):
        """Anything starting with / that isn't a command must NOT hit the agent."""
        with _Harness() as h, \
             patch("src.agents.conversation_agent.ConversationAgent") as MockAgent:
            result = await ws.telegram_bot_webhook(_request(_message("/nonsense")))
            await _drain()
        assert result == {"ok": True}
        MockAgent.assert_not_called()
        assert h.replies == []
