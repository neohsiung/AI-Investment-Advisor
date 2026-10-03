"""
Unit Tests for ShadowLedgerService and Shadow Ledger Repository (P2)
===================================================================
"""
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from sqlalchemy import create_engine

from src.repositories.shadow_ledger_repository import (
    AlchemyShadowLedgerRepository,
)
from src.services.shadow_ledger_service import (
    GraduationResult,
    ShadowLedgerService,
)
from src.services.smart_money_support_service import SmartMoneySupportResult


@pytest.fixture
def sqlite_engine():
    """In-memory SQLite engine for fast isolated repository testing."""
    return create_engine("sqlite:///:memory:")


@pytest.fixture
def shadow_repo(sqlite_engine):
    return AlchemyShadowLedgerRepository(engine=sqlite_engine)


@pytest.fixture
def mock_market():
    market = MagicMock()
    market.get_current_prices = AsyncMock(return_value={"AAPL": 100.0, "MSFT": 200.0, "GOOGL": 150.0})
    return market


@pytest.fixture
def mock_smart_money():
    sm = MagicMock()
    sm.calculate_smart_money_support.return_value = SmartMoneySupportResult(
        ticker="AAPL",
        current_price=100.0,
        anchored_vwap=96.0,
        point_of_control=94.5,
        value_area_high=98.0,
        value_area_low=92.0,
        high_volume_nodes=[96.0, 94.5],
        key_support_price=96.0,
        recommended_stop_loss=95.0,
        stop_loss_distance_pct=5.0,
        support_type="AVWAP_SUPPORT",
        anchor_date="2026-08-01",
        rationale="Synthetic test support",
    )
    return sm


@pytest.fixture
def mock_ticker_repo():
    tr = MagicMock()
    tr.upsert.return_value = True
    tr.add_log.return_value = True
    return tr


@pytest.fixture
def mock_settings_repo():
    sr = MagicMock()
    sr.get.side_effect = lambda uid, key: {
        "shadow_validation_min_days": 7,
        "shadow_validation_min_return": 0.0,
        "shadow_validation_max_drawdown": 5.0,
        "shadow_require_support_held": True,
    }.get(key, None)
    return sr


@pytest.fixture
def service(shadow_repo, mock_market, mock_smart_money, mock_ticker_repo, mock_settings_repo):
    return ShadowLedgerService(
        user_id="test-user-id",
        repo=shadow_repo,
        market=mock_market,
        smart_money=mock_smart_money,
        ticker_repo=mock_ticker_repo,
        settings_repo=mock_settings_repo,
    )


class TestShadowLedgerService:

    @pytest.mark.asyncio
    async def test_open_shadow_position_with_slippage_and_friction(self, service, mock_ticker_repo):
        pos = await service.open_shadow_position(
            ticker="AAPL",
            strategy_name="pyramid_stage1",
            allocated_capital=1000.0,
            entry_price=100.0,
            fee_pct=0.001,       # 0.1%
            slippage_pct=0.0005,  # 0.05%
        )

        assert pos is not None
        assert pos["ticker"] == "AAPL"
        assert pos["status"] == "OPEN"
        # 100 * (1 + 0.0005) = 100.05
        assert pos["entry_price"] == pytest.approx(100.05, 0.001)
        # Fee is $1.0, investable capital is $999.0 -> quantity = 999.0 / 100.05 ~ 9.985
        assert pos["simulated_quantity"] == pytest.approx(9.985, 0.01)
        assert pos["institutional_support_price"] == pytest.approx(96.0, 0.01)
        assert pos["support_breached"] is False
        assert pos["peak_price"] == pytest.approx(100.05, 0.001)

        # Verified ticker_universe status updated to 'shadow'
        mock_ticker_repo.upsert.assert_called_with("test-user-id", "AAPL", status="shadow")
        mock_ticker_repo.add_log.assert_called_once()

    @pytest.mark.asyncio
    async def test_open_shadow_position_idempotent_if_already_open(self, service):
        pos1 = await service.open_shadow_position(ticker="AAPL", entry_price=100.0)
        pos2 = await service.open_shadow_position(ticker="AAPL", entry_price=105.0)

        assert pos1["id"] == pos2["id"]
        assert pos2["entry_price"] == pos1["entry_price"]

    @pytest.mark.asyncio
    async def test_mark_to_market_gains_and_peak_drawdown(self, service):
        await service.open_shadow_position(ticker="AAPL", entry_price=100.0)

        # 1. Price rises to $110
        updated = await service.mark_to_market(prices_cache={"AAPL": 110.0})
        assert len(updated) == 1
        pos = updated[0]
        assert pos["current_price"] == 110.0
        assert pos["peak_price"] == 110.0
        assert pos["unrealized_pnl_pct"] > 9.0
        assert pos["max_drawdown_pct"] == 0.0

        # 2. Price pulls back to $104.50 (5% drawdown from peak $110.0)
        updated2 = await service.mark_to_market(prices_cache={"AAPL": 104.50})
        pos2 = updated2[0]
        assert pos2["current_price"] == 104.50
        assert pos2["peak_price"] == 110.0
        assert pos2["max_drawdown_pct"] == pytest.approx(5.0, 0.01)
        assert pos2["support_breached"] is False

    @pytest.mark.asyncio
    async def test_institutional_support_breach_detection(self, service):
        # Support is $96.0
        await service.open_shadow_position(ticker="AAPL", entry_price=100.0)

        # Price drops below institutional support ($96.0) to $94.0
        updated = await service.mark_to_market(prices_cache={"AAPL": 94.0})
        pos = updated[0]
        assert pos["current_price"] == 94.0
        assert pos["support_breached"] is True

    @pytest.mark.asyncio
    async def test_evaluate_graduation_in_progress_when_days_insufficient(self, service):
        await service.open_shadow_position(ticker="AAPL", entry_price=100.0)
        await service.mark_to_market(prices_cache={"AAPL": 105.0})

        # Set evaluation_days to 3 (< min_days=7)
        open_pos = service.repo.get_open_position("test-user-id", "AAPL")
        service.repo.update_position(open_pos["id"], evaluation_days=3)

        result = service.evaluate_graduation("AAPL", min_days=7)
        assert result.qualified is False
        assert result.status == "IN_PROGRESS"
        assert any("Observation period in progress" in r for r in result.reasons)

    @pytest.mark.asyncio
    async def test_evaluate_graduation_qualified(self, service):
        await service.open_shadow_position(ticker="AAPL", entry_price=100.0)
        await service.mark_to_market(prices_cache={"AAPL": 105.0})

        # Set evaluation_days to 8 (>= 7), positive return, drawdown = 0, support not breached
        open_pos = service.repo.get_open_position("test-user-id", "AAPL")
        service.repo.update_position(open_pos["id"], evaluation_days=8, max_drawdown_pct=2.0)

        result = service.evaluate_graduation("AAPL", min_days=7, min_return_pct=0.0, max_drawdown_pct=5.0)
        assert result.qualified is True
        assert result.status == "QUALIFIED"
        assert result.unrealized_pnl_pct > 0
        assert result.max_drawdown_pct <= 5.0

    @pytest.mark.asyncio
    async def test_evaluate_graduation_failed_when_support_breached(self, service):
        await service.open_shadow_position(ticker="AAPL", entry_price=100.0)
        await service.mark_to_market(prices_cache={"AAPL": 94.0})

        open_pos = service.repo.get_open_position("test-user-id", "AAPL")
        service.repo.update_position(open_pos["id"], evaluation_days=10, support_breached=True)

        result = service.evaluate_graduation("AAPL", require_support_held=True)
        assert result.qualified is False
        assert result.status == "FAILED"
        assert any("Smart Money Support breached" in r for r in result.reasons)

    @pytest.mark.asyncio
    async def test_graduate_position_promotes_to_active(self, service, mock_ticker_repo):
        await service.open_shadow_position(ticker="AAPL", entry_price=100.0)
        await service.mark_to_market(prices_cache={"AAPL": 106.0})

        res = await service.graduate_position("AAPL", reason="Graduation criteria met")
        assert res["success"] is True
        assert res["status"] == "GRADUATED"
        assert res["new_universe_status"] == "active"

        # Checked that DB shadow position is closed and ticker promoted to active
        open_pos = service.repo.get_open_position("test-user-id", "AAPL")
        assert open_pos is None

        closed = service.repo.list_positions("test-user-id", status="GRADUATED", ticker="AAPL")
        assert len(closed) == 1
        assert closed[0]["status"] == "GRADUATED"

        mock_ticker_repo.upsert.assert_called_with("test-user-id", "AAPL", status="active")
        assert any(call[1].get("action") == "shadow_graduated" for call in mock_ticker_repo.add_log.call_args_list)

    @pytest.mark.asyncio
    async def test_fail_position_demotes_to_candidate(self, service, mock_ticker_repo):
        await service.open_shadow_position(ticker="AAPL", entry_price=100.0)
        await service.mark_to_market(prices_cache={"AAPL": 90.0})

        res = await service.fail_position("AAPL", reason="Drawdown excessive", new_status="candidate")
        assert res["success"] is True
        assert res["status"] == "FAILED"
        assert res["new_universe_status"] == "candidate"

        open_pos = service.repo.get_open_position("test-user-id", "AAPL")
        assert open_pos is None

        mock_ticker_repo.upsert.assert_called_with("test-user-id", "AAPL", status="candidate")
        assert any(call[1].get("action") == "shadow_failed" for call in mock_ticker_repo.add_log.call_args_list)

    @pytest.mark.asyncio
    async def test_batch_step_and_evaluate(self, service, mock_market):
        mock_market.get_current_prices.return_value = {"AAPL": 100.0, "MSFT": 215.0}

        await service.open_shadow_position(ticker="AAPL", entry_price=100.0)
        await service.open_shadow_position(ticker="MSFT", entry_price=200.0)

        # MSFT is qualified: 8 days, PnL > 0 (215 > 200.10), MaxDD 1%
        msft_pos = service.repo.get_open_position("test-user-id", "MSFT")
        service.repo.update_position(msft_pos["id"], evaluation_days=8, max_drawdown_pct=1.0)

        # AAPL is in progress: 3 days
        aapl_pos = service.repo.get_open_position("test-user-id", "AAPL")
        service.repo.update_position(aapl_pos["id"], evaluation_days=3)

        summary = await service.batch_step_and_evaluate(auto_promote=True)
        assert summary["success"] is True
        assert summary["total_open"] == 2
        assert summary["graduated_count"] == 1
        assert summary["in_progress_count"] == 1
        assert summary["graduated"][0]["ticker"] == "MSFT"
        assert summary["in_progress"][0]["ticker"] == "AAPL"

    @pytest.mark.asyncio
    async def test_automated_trading_service_intercepts_shadow_ticker_buy(self, shadow_repo, mock_ticker_repo):
        from src.services.automated_trading_service import AutomatedTradingService

        mock_ticker_repo.get_all.return_value = [{"ticker": "NVDA", "status": "shadow"}]
        mock_settings = MagicMock()
        mock_settings.get.return_value = "true"  # ai_trading_enabled

        auto_trader = AutomatedTradingService(settings_repo=mock_settings)

        with patch("src.repositories.ticker_universe_repository.TickerUniverseRepository", return_value=mock_ticker_repo), \
             patch("src.services.trading_protections_service.TradingProtectionsService.check", return_value=None), \
             patch("src.services.shadow_ledger_service.ShadowLedgerService.open_shadow_position", new_callable=AsyncMock) as mock_open:
            mock_open.return_value = {"id": "shadow-nvda-123", "ticker": "NVDA"}

            res = await auto_trader.evaluate_and_execute_trade(
                user_id="test-user-id",
                ticker="NVDA",
                action="BUY",
                quantity=1000.0,
                confidence_score=85,
                strategy_name="growth_momentum",
            )

            assert res["status"] == "shadow_executed"
            assert res["ticker"] == "NVDA"
            assert res["shadow_position_id"] == "shadow-nvda-123"
            mock_open.assert_called_once_with(
                ticker="NVDA",
                strategy_name="growth_momentum",
                allocated_capital=1000.0,
                notes="Auto-routed shadow BUY (Confidence: 85)"
            )

    @pytest.mark.asyncio
    async def test_universe_lifecycle_screen_and_admit_routes_to_shadow(self, mock_market, mock_smart_money):
        from src.services.universe_lifecycle_service import UniverseLifecycleService
        from src.services.quality_gate_service import QualityAssessment

        repo = MagicMock()
        repo.get_all.return_value = []
        repo.upsert.return_value = True
        repo.add_log.return_value = True

        qg = MagicMock()
        qg.evaluate_ticker = AsyncMock(return_value=QualityAssessment(
            ticker="TSLA",
            passed=True,
            overall_score=8.5,
            hard_gates_passed=True,
            hard_gate_details={},
            fundamental_score=8.0,
            technical_score=9.0,
            liquidity_score=8.5,
            reasons=[],
            metrics={},
        ))

        settings = MagicMock()
        settings.get_setting.side_effect = lambda k: {
            "universe_max_active_tickers": 5,
            "universe_min_quality_score": 6.5,
            "universe_require_shadow_validation": True,
        }.get(k, None)

        mock_market.get_financials.return_value = {}

        service = UniverseLifecycleService(
            user_id="test-user-id",
            repo=repo,
            market=mock_market,
            quality_gate=qg,
        )
        service.settings = settings

        with patch("src.services.shadow_ledger_service.ShadowLedgerService.open_shadow_position", new_callable=AsyncMock) as mock_open:
            mock_open.return_value = {"id": "shadow-tsla-456", "ticker": "TSLA"}

            admitted = await service.screen_and_admit_candidates(
                candidate_pool=["TSLA"],
                max_active=5,
                require_shadow_validation=True,
            )

            assert len(admitted) == 1
            assert admitted[0]["ticker"] == "TSLA"
            assert admitted[0]["status"] == "shadow"
            repo.upsert.assert_called_with(
                "test-user-id",
                "TSLA",
                company_name="TSLA",
                sector="",
                industry="",
                status="shadow"
            )
            mock_open.assert_called_once()

    def test_run_shadow_ledger_eval_task(self):
        from src.infrastructure.tasks import run_shadow_ledger_eval

        with patch("src.services.shadow_ledger_service.ShadowLedgerService.batch_step_and_evaluate", new_callable=AsyncMock) as mock_batch:
            mock_batch.return_value = {
                "success": True,
                "total_open": 3,
                "graduated_count": 1,
                "failed_count": 0,
                "in_progress_count": 2,
            }

            res = run_shadow_ledger_eval(user_id="test-user-id", auto_promote=True)
            assert isinstance(res, dict)
            assert res["success"] is True
            assert res["graduated_count"] == 1
            mock_batch.assert_called_once_with(auto_promote=True)

