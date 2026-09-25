"""
Unit Tests for Strategy Discovery Service
=========================================
驗證策略自主探索、參數網格掃描、實盤門檻篩選與策略晉升實盤註冊。
"""
import pytest

from src.domain.strategy_contract import MarketRegimeType
from src.services.strategy_discovery_service import (
    DiscoveryCandidate,
    StrategyDiscoveryService,
)
from src.services.strategy_registry import StrategyRegistry


class TestStrategyDiscoveryService:
    @pytest.fixture
    def discovery_service(self):
        return StrategyDiscoveryService()

    def test_evaluate_candidate_metrics_pass(self, discovery_service):
        """Verify passing metrics satisfy the validation thresholds."""
        good_metrics = {
            "sharpe": 1.45,
            "max_drawdown_pct": 12.5,
            "total_trades": 25.0,
            "win_rate": 88.0,
        }
        passed, reasons = discovery_service.evaluate_candidate_metrics(
            metrics=good_metrics,
            initial_cash=10000.0,
            final_cash=14500.0,
            buy_and_hold_return_pct=15.0,
        )
        assert passed is True
        assert len(reasons) == 0

    def test_evaluate_candidate_metrics_fail(self, discovery_service):
        """Verify failing metrics are caught with detailed reasons."""
        bad_metrics = {
            "sharpe": 0.40,               # < 0.8
            "max_drawdown_pct": 35.0,     # > 20%
            "total_trades": 4.0,          # < 10
        }
        passed, reasons = discovery_service.evaluate_candidate_metrics(
            metrics=bad_metrics,
            initial_cash=10000.0,
            final_cash=9500.0,            # < 0% return
            buy_and_hold_return_pct=10.0, # underperformed
        )
        assert passed is False
        assert len(reasons) >= 3

    def test_sweep_vix_panic_grid(self, discovery_service):
        """Verify grid sweep correctly simulates and ranks parameter sets."""
        # Generate synthetic panic cycles: VIX spikes to 42, market drops then rebounds
        vix_series = [
            18.0, 22.0, 36.0, 43.0, 48.0, 39.0, 31.0, 24.0, 19.0, 17.0,
            16.0, 20.0, 37.0, 44.0, 52.0, 41.0, 29.0, 23.0, 18.0, 16.0,
            15.0, 21.0, 38.0, 45.0, 50.0, 42.0, 30.0, 22.0, 19.0, 15.0,
        ] * 4  # 120 bars, 12 cycles
        price_series = [
            100.0, 97.0, 93.0, 89.0, 86.0, 92.0, 98.0, 104.0, 107.0, 108.0,
            108.0, 105.0, 100.0, 94.0, 90.0, 96.0, 102.0, 109.0, 112.0, 114.0,
            114.0, 110.0, 104.0, 98.0, 95.0, 101.0, 107.0, 115.0, 118.0, 120.0,
        ] * 4

        report = discovery_service.sweep_vix_panic_grid(
            vix_series=vix_series,
            price_series=price_series,
            entry_thresholds=[40.0],
            exit_thresholds=[25.0],
            leverage_options=[1, 2],
            stop_loss_pcts=[6.0],
            benchmark_return_pct=5.0,
        )

        assert report.total_scenarios_tested > 0
        assert report.regime == MarketRegimeType.VOLATILITY_EXTREME
        # All scenarios should be tested
        for cand in report.viable_candidates:
            assert cand.is_validated is True
            assert cand.metrics["total_trades"] >= 10

    def test_sweep_invalid_series(self, discovery_service):
        """Verify sweep returns empty report on invalid or mismatched series."""
        report = discovery_service.sweep_vix_panic_grid(
            vix_series=[20.0, 30.0],
            price_series=[100.0],
        )
        assert report.total_scenarios_tested == 0
        assert len(report.viable_candidates) == 0
        assert report.best_candidate is None

    def test_promote_candidate(self, discovery_service):
        """Verify candidate promotion lifecycle into StrategyRegistry."""
        # 1. Unvalidated candidate cannot be promoted
        invalid_candidate = DiscoveryCandidate(
            strategy_id="invalid_strat_v1",
            regime=MarketRegimeType.VOLATILITY_EXTREME,
            parameters={"entry_vix_threshold": 40.0, "exit_vix_threshold": 25.0},
            metrics={"sharpe": 0.2},
            is_validated=False,
            validation_failures=["Sharpe too low"],
        )
        assert discovery_service.promote_candidate(invalid_candidate) is False
        assert StrategyRegistry.get("invalid_strat_v1") is None

        # 2. Validated candidate can be promoted and evaluated
        valid_candidate = DiscoveryCandidate(
            strategy_id="discovered_panic_v2",
            regime=MarketRegimeType.VOLATILITY_EXTREME,
            parameters={
                "entry_vix_threshold": 42.0,
                "exit_vix_threshold": 24.0,
                "leverage": 2,
                "stop_loss_pct": 5.0,
            },
            metrics={"sharpe": 1.6, "total_trades": 18.0},
            is_validated=True,
            validation_failures=[],
        )
        promoted = discovery_service.promote_candidate(valid_candidate)
        assert promoted is True

        contract = StrategyRegistry.get("discovered_panic_v2")
        assert contract is not None
        assert contract.strategy_id == "discovered_panic_v2"
        assert contract.risk_budget.max_allowed_leverage == 2

        # Test dynamic contract evaluation
        entry_plan = contract.evaluate_entry({"vix": 45.0})
        assert entry_plan is not None
        assert entry_plan.action == "BUY"
        assert entry_plan.target_leverage == 2

        exit_plan = contract.evaluate_exit(None, {"vix": 22.0})
        assert exit_plan is not None
        assert exit_plan.action == "SELL"

    @pytest.mark.asyncio
    async def test_run_evolution_cycle_success(self, discovery_service):
        """Verify full autonomous strategy evolution cycle execution and report synthesis."""
        from unittest.mock import AsyncMock, patch

        with patch("src.services.notification_service.NotificationService.create_with_settings") as mock_notif_factory:
            mock_notif = AsyncMock()
            mock_notif_factory.return_value = mock_notif

            res = await discovery_service.run_evolution_cycle(user_id="u_test_evolution", force=True)
            assert res["status"] == "success"
            assert res["scenarios_tested"] > 0
            assert "行動" in res["report"]
            assert "狀況影響" in res["report"]
            assert "交易策略改變的行動" in res["report"]
            assert mock_notif.notify_all.called

    @pytest.mark.asyncio
    async def test_run_evolution_cycle_disabled_skip(self, discovery_service):
        """Verify cycle skips when strategy_evolution_enabled is false and force is false."""
        from unittest.mock import patch

        with patch("src.services.settings_service.SettingsService.get_setting", return_value="false"):
            res = await discovery_service.run_evolution_cycle(user_id="u_test_skip", force=False)
            assert res["status"] == "skipped"

