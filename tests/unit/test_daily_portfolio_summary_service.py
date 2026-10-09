import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from src.domain.trading import Position
from src.services.daily_portfolio_summary_service import DailyPortfolioSummaryService
from src.services.conversation_router import ConversationRouter


def test_daily_portfolio_summary_generation_zero_trades():
    async def _test():
        user_id = "00000000-0000-4000-a000-000000000001"
        svc = DailyPortfolioSummaryService(user_id=user_id)

        mock_positions = [
            Position(
                symbol="AAPL",
                quantity=1.5,
                open_price=200.0,
                current_price=220.0,
                market_value=330.0,
                unrealized_pnl=30.0,
            ),
            Position(
                symbol="NVDA",
                quantity=0.8,
                open_price=100.0,
                current_price=125.0,
                market_value=100.0,
                unrealized_pnl=20.0,
            )
        ]
        mock_portfolio = {
            "total_equity": 500.0,
            "total_cash": 70.0,
            "positions": mock_positions,
        }

        with patch("src.services.portfolio_aggregator_service.PortfolioAggregatorService.get_aggregated_portfolio", new_callable=AsyncMock) as mock_agg, \
             patch("src.repositories.transaction_repository.AlchemyTransactionRepository.get_all_by_user_df") as mock_tx, \
             patch("src.repositories.transaction_repository.AlchemyTransactionRepository.calculate_net_invested_capital", return_value=550.0), \
             patch.object(svc, "_get_macro_context", return_value={"spy": "560.0", "vix": "15.2", "spread": "0.15%", "note": "低波動擴張"}):
            
            mock_agg.return_value = mock_portfolio
            import pandas as pd
            mock_tx.return_value = pd.DataFrame()  # 0 trades today

            summary = await svc.generate_summary()

            assert "Daily Portfolio & Operations Summary" in summary["title"]
            assert summary["total_equity"] == 500.0
            assert summary["total_cash"] == 70.0
            assert summary["positions_count"] == 2
            assert summary["trades_count"] == 0

            md = summary["markdown"]
            assert "AAPL" in md
            assert "NVDA" in md
            assert "今日實盤成交筆數" in md
            assert "0 筆" in md
            assert "維持長線持有決策依據" in md
            assert "Net Δ ≥ 2.0" in md or "未達機會成本換庫門檻" in md
            assert "SPY" in md
            assert "VIX" in md
            assert "系統自學與自我演化成果" in md
            assert "現有 2 檔部位" in md
            assert "19 檔" not in md

    asyncio.run(_test())


def test_daily_portfolio_summary_true_capital_audit_loss_scenario():
    """
    Validates faithful reporting when total account is in loss vs deposited capital,
    even if current holdings have a slight positive unrealized PnL.
    """
    async def _test():
        user_id = "00000000-0000-4000-a000-000000000001"
        svc = DailyPortfolioSummaryService(user_id=user_id)

        mock_positions = [
            Position(
                symbol="AAPL",
                quantity=0.297885,
                open_price=335.70,
                current_price=340.60,
                market_value=101.41,
                unrealized_pnl=1.46,
            ),
            Position(
                symbol="MSFT",
                quantity=0.189075,
                open_price=528.89,
                current_price=522.33,
                market_value=98.81,
                unrealized_pnl=-1.24,
            ),
            Position(
                symbol="META",
                quantity=0.122584,
                open_price=736.80,
                current_price=719.42,
                market_value=88.19,
                unrealized_pnl=-2.36,
            ),
        ]
        # Total equity $1692.50 vs deposited $1711.00 -> Loss -$18.50 (-1.08%)
        mock_portfolio = {
            "total_equity": 1692.50,
            "total_cash": 1404.09,
            "positions": mock_positions,
        }

        with patch("src.services.portfolio_aggregator_service.PortfolioAggregatorService.get_aggregated_portfolio", new_callable=AsyncMock) as mock_agg, \
             patch("src.repositories.transaction_repository.AlchemyTransactionRepository.get_all_by_user_df") as mock_tx, \
             patch.object(svc.settings_svc, "get_setting", side_effect=lambda k: 1711.0 if k == "initial_capital_deposited_usd" else None), \
             patch.object(svc, "_get_macro_context", return_value={"spy": "560.0", "vix": "20.0", "spread": "0.15%", "note": "中性震盪"}):

            mock_agg.return_value = mock_portfolio
            import pandas as pd
            mock_tx.return_value = pd.DataFrame()

            summary = await svc.generate_summary()

            assert summary["total_equity"] == 1692.50
            assert summary["total_cash"] == 1404.09
            assert summary["invested_capital"] == 1711.00
            assert summary["cumulative_pnl"] == -18.50
            assert round(summary["cumulative_pnl_pct"], 2) == -1.08
            assert summary["positions_count"] == 3
            assert summary["defensive_reserve_usd"] == 338.50
            assert summary["deployable_cash"] == 1065.59

            md = summary["markdown"]
            assert "累計存入本金基準 (Deposited Capital)" in md
            assert "$1,711.00 USD" in md
            assert "總資產淨值 (Net Liquidation Value)" in md
            assert "$1,692.50 USD" in md
            assert "帳戶全週期真實累計損益 (Cumulative Net PnL)" in md
            assert "-$18.50 (-1.08%)" in md
            assert "🔴" in md
            assert "剛性防守現金儲備 (20% 保底)" in md
            assert "$338.50 USD" in md
            assert "可動用建倉現金 (Deployable Cash)" in md
            assert "$1,065.59 USD" in md
            assert "現有 3 檔部位" in md

    asyncio.run(_test())


def test_daily_portfolio_summary_true_capital_audit_profit_scenario():
    """
    Validates faithful reporting when total account is in profit vs deposited capital.
    """
    async def _test():
        user_id = "00000000-0000-4000-a000-000000000001"
        svc = DailyPortfolioSummaryService(user_id=user_id)

        mock_positions = [
            Position(
                symbol="NVDA",
                quantity=2.0,
                open_price=100.0,
                current_price=150.0,
                market_value=300.0,
                unrealized_pnl=100.0,
            )
        ]
        mock_portfolio = {
            "total_equity": 1200.0,
            "total_cash": 900.0,
            "positions": mock_positions,
        }

        with patch("src.services.portfolio_aggregator_service.PortfolioAggregatorService.get_aggregated_portfolio", new_callable=AsyncMock) as mock_agg, \
             patch("src.repositories.transaction_repository.AlchemyTransactionRepository.get_all_by_user_df") as mock_tx, \
             patch.object(svc.settings_svc, "get_setting", side_effect=lambda k: 1000.0 if k == "initial_capital_deposited_usd" else None), \
             patch.object(svc, "_get_macro_context", return_value={"spy": "560.0", "vix": "14.0", "spread": "0.15%", "note": "多頭牛市"}):

            mock_agg.return_value = mock_portfolio
            import pandas as pd
            mock_tx.return_value = pd.DataFrame()

            summary = await svc.generate_summary()

            assert summary["total_equity"] == 1200.0
            assert summary["invested_capital"] == 1000.0
            assert summary["cumulative_pnl"] == 200.0
            assert summary["cumulative_pnl_pct"] == 20.0

            md = summary["markdown"]
            assert "+$200.00 (+20.00%)" in md
            assert "🟢" in md

    asyncio.run(_test())


def test_daily_portfolio_summary_dispatch():
    async def _test():
        user_id = "00000000-0000-4000-a000-000000000001"
        svc = DailyPortfolioSummaryService(user_id=user_id)

        mock_summary = {
            "title": "📊 每日投資組合與操作總結 — 2026-09-22",
            "markdown": "## 測試總結內容",
            "total_equity": 1000.0,
            "total_cash": 100.0,
            "positions_count": 1,
            "trades_count": 0,
        }

        with patch.object(svc, "_has_already_dispatched_today", return_value=(False, None)), \
             patch.object(svc, "generate_summary", new_callable=AsyncMock, return_value=mock_summary), \
             patch("src.repositories.report_repository.AlchemyReportRepository.save", return_value="rep-123") as mock_save, \
             patch("src.services.notification_service.NotificationService.create_with_settings") as mock_notif_factory, \
             patch("src.infrastructure.cache.redis_client.get_redis_sync", side_effect=Exception("no redis")):

            mock_notif_svc = MagicMock()
            mock_notif_svc.notify_all = AsyncMock(return_value={"EmailAdapter": True, "WebAdapter": True})
            mock_notif_factory.return_value = mock_notif_svc

            res = await svc.generate_and_dispatch()

            assert res["status"] == "success"
            assert res["report_id"] == "rep-123"
            mock_save.assert_called_once()
            
            mock_notif_svc.notify_all.assert_called_once()
            _, kwargs = mock_notif_svc.notify_all.call_args
            assert kwargs["channels"] is None
            assert kwargs["category"] == "report"

    asyncio.run(_test())


def test_daily_portfolio_summary_skips_when_already_dispatched():
    async def _test():
        user_id = "00000000-0000-4000-a000-000000000001"
        svc = DailyPortfolioSummaryService(user_id=user_id)

        with patch.object(svc, "_has_already_dispatched_today", return_value=(True, "Report rep-existing exists")), \
             patch.object(svc, "generate_summary", new_callable=AsyncMock) as mock_gen:

            res = await svc.generate_and_dispatch(force_report=False)

            assert res["status"] == "skipped"
            assert res["reason"] == "already_sent_today"
            mock_gen.assert_not_called()

    asyncio.run(_test())


def test_daily_portfolio_summary_throttles_force_report():
    async def _test():
        user_id = "00000000-0000-4000-a000-000000000001"
        svc = DailyPortfolioSummaryService(user_id=user_id)

        with patch.object(svc, "_is_throttled", return_value=(True, "Report sent 5m ago")), \
             patch.object(svc, "generate_summary", new_callable=AsyncMock) as mock_gen:

            res = await svc.generate_and_dispatch(force_report=True, bypass_throttle=False)

            assert res["status"] == "skipped"
            assert res["reason"] == "throttled"
            mock_gen.assert_not_called()

    asyncio.run(_test())


def test_daily_portfolio_summary_bypass_throttle():
    async def _test():
        user_id = "00000000-0000-4000-a000-000000000001"
        svc = DailyPortfolioSummaryService(user_id=user_id)

        mock_summary = {
            "title": "📊 每日投資組合與操作總結 — 2026-09-22",
            "markdown": "## 測試總結內容",
            "total_equity": 1000.0,
            "total_cash": 100.0,
            "positions_count": 1,
            "trades_count": 0,
        }

        with patch.object(svc, "generate_summary", new_callable=AsyncMock, return_value=mock_summary), \
             patch("src.repositories.report_repository.AlchemyReportRepository.save", return_value="rep-forced"), \
             patch("src.services.notification_service.NotificationService.create_with_settings") as mock_notif_factory, \
             patch("src.infrastructure.cache.redis_client.get_redis_sync", side_effect=Exception("no redis")):

            mock_notif_svc = MagicMock()
            mock_notif_svc.notify_all = AsyncMock(return_value={"EmailAdapter": True, "WebAdapter": True})
            mock_notif_factory.return_value = mock_notif_svc

            res = await svc.generate_and_dispatch(force_report=True, bypass_throttle=True)

            assert res["status"] == "success"
            assert res["report_id"] == "rep-forced"

    asyncio.run(_test())


def test_conversation_router_system_commands():
    """
    Tests direct 0-LLM system commands (/status, /holdings, /batch, /guard) in ConversationRouter.
    """
    async def _test():
        router = ConversationRouter()
        adapter = MagicMock()

        # 1. /status command test
        mock_summary = {
            "total_equity": 1692.50,
            "total_cash": 1404.09,
            "invested_capital": 1711.00,
            "cumulative_pnl": -18.50,
            "cumulative_pnl_pct": -1.08,
            "total_unrealized_pnl": 1.40,
            "closed_realized_pnl": -19.90,
            "defensive_reserve_usd": 338.50,
            "deployable_cash": 1065.59,
            "positions_count": 3,
        }
        with patch("src.services.daily_portfolio_summary_service.DailyPortfolioSummaryService.generate_summary", new_callable=AsyncMock, return_value=mock_summary):
            res = await router.route(
                adapter=adapter,
                channel_user_id="tg_123",
                text="/status",
                resolved_user_id="00000000-0000-4000-a000-000000000001",
                channel_type="telegram"
            )
            assert "實盤真實驗資與對帳總結" in res
            assert "$1,692.50 USD" in res
            assert "$1,711.00 USD" in res
            assert "-$18.50 (-1.08%)" in res
            assert "🔴" in res
            assert "$338.50 USD" in res

        # 2. Chinese keyword '資產' test
        with patch("src.services.daily_portfolio_summary_service.DailyPortfolioSummaryService.generate_summary", new_callable=AsyncMock, return_value=mock_summary):
            res_zh = await router.route(
                adapter=adapter,
                channel_user_id="tg_123",
                text="資產",
                resolved_user_id="00000000-0000-4000-a000-000000000001",
                channel_type="telegram"
            )
            assert "實盤真實驗資與對帳總結" in res_zh

        # 3. /holdings command test
        mock_portfolio = {
            "total_equity": 1692.50,
            "positions": [
                Position(symbol="AAPL", quantity=0.2978, open_price=335.70, current_price=340.60, market_value=101.41, unrealized_pnl=1.46)
            ]
        }
        with patch("src.services.portfolio_aggregator_service.PortfolioAggregatorService.get_aggregated_portfolio", new_callable=AsyncMock, return_value=mock_portfolio):
            res_holdings = await router.route(
                adapter=adapter,
                channel_user_id="tg_123",
                text="/holdings",
                resolved_user_id="00000000-0000-4000-a000-000000000001",
                channel_type="telegram"
            )
            assert "當前實盤持倉清單" in res_holdings
            assert "AAPL" in res_holdings
            assert "101.41" in res_holdings

        # 4. /guard command test
        with patch("src.services.settings_service.SettingsService.get_setting", side_effect=lambda k: True if k == "enable_slippage_guard" else 0.0015), \
             patch("src.utils.market_clock.MarketClock.is_market_open", return_value=False), \
             patch("src.services.slippage_guard_service.SlippageGuardService.is_opening_auction_window", return_value=False):
            res_guard = await router.route(
                adapter=adapter,
                channel_user_id="tg_123",
                text="/guard",
                resolved_user_id="00000000-0000-4000-a000-000000000001",
                channel_type="telegram"
            )
            assert "開盤防滑點守衛與價差熔斷狀態" in res_guard
            assert "0.15% (15 bps)" in res_guard

    asyncio.run(_test())


def test_daily_portfolio_summary_self_evolution_length_constraints():
    """
    Verify the daily self-evolution list format constraints:
    Each item: headline ~10 words/characters, description <= 30 words/characters.
    """
    user_id = "00000000-0000-4000-a000-000000000001"
    svc = DailyPortfolioSummaryService(user_id=user_id)
    achievements = svc._get_self_evolution_achievements()

    assert len(achievements) > 0
    for ach in achievements:
        title = ach["title"]
        desc = ach["desc"]
        # Headline around 10 words/characters (allowing emoji prefix)
        assert len(title) <= 12, f"Title too long: {title}"
        # Description strictly within 30 characters
        assert len(desc) <= 30, f"Description exceeds 30 characters: {desc}"
