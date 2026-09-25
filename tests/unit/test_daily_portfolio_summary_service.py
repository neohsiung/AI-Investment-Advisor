import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from src.domain.trading import Position
from src.services.daily_portfolio_summary_service import DailyPortfolioSummaryService


@pytest.mark.asyncio
async def test_daily_portfolio_summary_generation_zero_trades():
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
        assert "Δ ≥ 2.0" in md or "未達機會成本換庫門檻" in md
        assert "SPY" in md
        assert "VIX" in md
        assert "系統自學與自我演化成果" in md


@pytest.mark.asyncio
async def test_daily_portfolio_summary_dispatch():
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
        
        # Verify notification dispatched dynamically to user configured channels
        mock_notif_svc.notify_all.assert_called_once()
        _, kwargs = mock_notif_svc.notify_all.call_args
        assert kwargs["channels"] is None
        assert kwargs["category"] == "report"


@pytest.mark.asyncio
async def test_daily_portfolio_summary_skips_when_already_dispatched():
    user_id = "00000000-0000-4000-a000-000000000001"
    svc = DailyPortfolioSummaryService(user_id=user_id)

    with patch.object(svc, "_has_already_dispatched_today", return_value=(True, "Report rep-existing exists")), \
         patch.object(svc, "generate_summary", new_callable=AsyncMock) as mock_gen:

        res = await svc.generate_and_dispatch(force_report=False)

        assert res["status"] == "skipped"
        assert res["reason"] == "already_sent_today"
        mock_gen.assert_not_called()


@pytest.mark.asyncio
async def test_daily_portfolio_summary_throttles_force_report():
    user_id = "00000000-0000-4000-a000-000000000001"
    svc = DailyPortfolioSummaryService(user_id=user_id)

    with patch.object(svc, "_is_throttled", return_value=(True, "Report sent 5m ago")), \
         patch.object(svc, "generate_summary", new_callable=AsyncMock) as mock_gen:

        # force_report=True but not bypass_throttle
        res = await svc.generate_and_dispatch(force_report=True, bypass_throttle=False)

        assert res["status"] == "skipped"
        assert res["reason"] == "throttled"
        mock_gen.assert_not_called()


@pytest.mark.asyncio
async def test_daily_portfolio_summary_bypass_throttle():
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


@pytest.mark.asyncio
async def test_daily_portfolio_summary_self_evolution_length_constraints():
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
