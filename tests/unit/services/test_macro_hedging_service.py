"""
Unit Tests for Macro Hedging Service (MacroHedgingService)
=========================================================
驗證跨市場宏觀波動率體制自動避險服務之體制分類、投組 Beta 曝險度量、
動態防守現金擴增、高 Beta 標的修剪推薦、反向 ETF 對沖配置與策略契約適配。
"""
import pytest
from unittest.mock import MagicMock

from src.domain.strategy_contract import MarketRegimeType
from src.services.macro_hedging_service import (
    HedgingActionType,
    HedgingSeverity,
    MacroHedgingService,
    MacroVolatilityHedgeContract,
)


class TestMacroHedgingService:
    @pytest.fixture
    def mock_settings_service(self):
        settings = MagicMock()
        config_map = {
            "enable_macro_volatility_hedging": True,
            "macro_hedge_vix_threshold": 30.0,
            "macro_hedge_target_cash_ratio": 0.25,
            "macro_hedge_instrument": "SH",
            "enable_inverse_etf_hedge": False,
            "target_cash_ratio": 0.10,
        }
        settings.get_setting.side_effect = lambda k, default=None, user_id=None: config_map.get(k, default)
        return settings

    @pytest.fixture
    def mock_winner_service(self):
        service = MagicMock()
        service.get_certified_winners.return_value = [{"symbol": "NVDA"}]
        return service

    @pytest.fixture
    def hedging_service(self, mock_settings_service, mock_winner_service):
        return MacroHedgingService(
            settings_service=mock_settings_service,
            winner_service=mock_winner_service,
        )

    def test_classify_severity(self, hedging_service):
        """Verify severity transitions across different volatility and stress thresholds."""
        # Normal
        assert hedging_service.classify_severity(vix=18.0, vix_z_score=0.5) == HedgingSeverity.NORMAL

        # Elevated
        assert hedging_service.classify_severity(vix=25.0, vix_z_score=1.5) == HedgingSeverity.ELEVATED
        assert hedging_service.classify_severity(vix=19.0, vix_z_score=1.9) == HedgingSeverity.ELEVATED
        assert hedging_service.classify_severity(vix=19.0, macro_stress_bias=-0.2) == HedgingSeverity.ELEVATED
        assert hedging_service.classify_severity(vix=19.0, yield_spread=-0.1) == HedgingSeverity.ELEVATED

        # High
        assert hedging_service.classify_severity(vix=32.0, vix_z_score=1.0) == HedgingSeverity.HIGH
        assert hedging_service.classify_severity(vix=22.0, vix_z_score=2.6) == HedgingSeverity.HIGH
        assert hedging_service.classify_severity(vix=22.0, macro_stress_bias=-0.35) == HedgingSeverity.HIGH
        assert hedging_service.classify_severity(vix=22.0, yield_spread=-0.6) == HedgingSeverity.HIGH

        # Critical
        assert hedging_service.classify_severity(vix=42.0, vix_z_score=1.0) == HedgingSeverity.CRITICAL
        assert hedging_service.classify_severity(vix=28.0, vix_z_score=3.2) == HedgingSeverity.CRITICAL
        assert hedging_service.classify_severity(vix=25.0, macro_stress_bias=-0.65) == HedgingSeverity.CRITICAL

    def test_compute_portfolio_metrics(self, hedging_service):
        """Verify portfolio weighted beta and exposure calculations."""
        portfolio = {
            "total_nlv": 100000.0,
            "cash_balance": 10000.0,  # 10% cash
            "positions": [
                {"symbol": "NVDA", "market_value": 45000.0, "beta": 1.8},
                {"symbol": "AAPL", "market_value": 45000.0, "beta": 1.0},
            ],
        }
        total_nlv, cash_ratio, gross_exposure, weighted_beta = hedging_service.compute_portfolio_metrics(portfolio)
        assert total_nlv == 100000.0
        assert pytest.approx(cash_ratio, 0.01) == 0.10
        assert pytest.approx(gross_exposure, 0.01) == 0.90
        # (45000*1.8 + 45000*1.0) / 90000 = 1.4
        assert pytest.approx(weighted_beta, 0.01) == 1.40

    def test_determine_target_cash_ratio(self, hedging_service):
        """Verify dynamic scaling of target cash ratio across severities."""
        base = 0.10
        max_target = 0.25

        assert hedging_service.determine_target_cash_ratio(base, HedgingSeverity.NORMAL, max_target) == 0.10
        assert hedging_service.determine_target_cash_ratio(base, HedgingSeverity.ELEVATED, max_target) == 0.15
        assert hedging_service.determine_target_cash_ratio(base, HedgingSeverity.HIGH, max_target) == 0.20
        assert hedging_service.determine_target_cash_ratio(base, HedgingSeverity.CRITICAL, max_target) == 0.25

    def test_identify_trim_candidates_with_winner_protection(self, hedging_service):
        """Verify candidates with high beta/lower return are trimmed first, protecting winners."""
        positions = [
            {"symbol": "NVDA", "market_value": 30000.0, "beta": 2.0, "unrealized_pnl_pct": 0.50},  # Winner!
            {"symbol": "SPEC_HIGH_BETA", "market_value": 20000.0, "beta": 2.2, "unrealized_pnl_pct": -0.05},
            {"symbol": "STABLE_CO", "market_value": 20000.0, "beta": 0.8, "unrealized_pnl_pct": 0.02},
        ]
        # Needs $5,000 cash raised
        recs = hedging_service.identify_trim_candidates(
            positions=positions,
            required_cash_raise=5000.0,
            total_nlv=100000.0,
            user_id="user_123",
        )
        assert len(recs) >= 1
        # SPEC_HIGH_BETA has highest trim score (beta=2.2, loss=-5%, non-winner)
        assert recs[0].ticker == "SPEC_HIGH_BETA"
        assert recs[0].action == HedgingActionType.TRIM_HIGH_BETA
        assert recs[0].suggested_amount == 5000.0

    def test_evaluate_hedging_disabled(self, mock_settings_service, mock_winner_service):
        """Verify service returns inactive when disabled via settings."""
        mock_settings_service.get_setting.side_effect = lambda k, default=None, user_id=None: (
            False if k == "enable_macro_volatility_hedging" else default
        )
        service = MacroHedgingService(settings_service=mock_settings_service, winner_service=mock_winner_service)
        eval_result = service.evaluate_hedging(
            portfolio={"total_nlv": 50000.0, "cash_balance": 5000.0, "positions": []},
            vix=45.0,
            vix_z_score=3.5,
        )
        assert eval_result.is_hedging_active is False
        assert "停用" in eval_result.summary

    def test_evaluate_hedging_active_scaling(self, hedging_service):
        """Verify dynamic cash scaling under high volatility shock."""
        portfolio = {
            "total_nlv": 100000.0,
            "cash_balance": 5000.0,  # 5% cash (insufficient vs 20% target)
            "positions": [
                {"symbol": "TSLA", "market_value": 45000.0, "beta": 1.9, "unrealized_pnl_pct": -0.02},
                {"symbol": "AAPL", "market_value": 50000.0, "beta": 1.0, "unrealized_pnl_pct": 0.10},
            ],
        }
        eval_result = hedging_service.evaluate_hedging(
            portfolio=portfolio,
            vix=35.0,
            vix_z_score=2.7,
            macro_stress_bias=-0.35,
        )
        assert eval_result.is_hedging_active is True
        assert eval_result.severity == HedgingSeverity.HIGH
        assert eval_result.target_cash_ratio >= 0.20
        assert eval_result.required_cash_raise > 0
        assert any(r.action == HedgingActionType.TRIM_HIGH_BETA for r in eval_result.recommendations)

    def test_evaluate_hedging_with_inverse_etf(self, mock_settings_service, mock_winner_service):
        """Verify inverse ETF allocation recommendation when enabled."""
        config_map = {
            "enable_macro_volatility_hedging": True,
            "macro_hedge_vix_threshold": 30.0,
            "macro_hedge_target_cash_ratio": 0.25,
            "macro_hedge_instrument": "SH",
            "enable_inverse_etf_hedge": True,
            "target_cash_ratio": 0.10,
        }
        mock_settings_service.get_setting.side_effect = lambda k, default=None, user_id=None: config_map.get(k, default)
        service = MacroHedgingService(settings_service=mock_settings_service, winner_service=mock_winner_service)

        portfolio = {
            "total_nlv": 100000.0,
            "cash_balance": 30000.0,  # Cash already ample
            "positions": [
                {"symbol": "AAPL", "market_value": 70000.0, "beta": 1.0, "unrealized_pnl_pct": 0.15},
            ],
        }
        eval_result = service.evaluate_hedging(
            portfolio=portfolio,
            vix=42.0,
            vix_z_score=3.1,
        )
        assert eval_result.is_hedging_active is True
        assert eval_result.severity == HedgingSeverity.CRITICAL
        # Should recommend 10% inverse ETF in CRITICAL
        inverse_recs = [r for r in eval_result.recommendations if r.action == HedgingActionType.BUY_INVERSE_HEDGE]
        assert len(inverse_recs) == 1
        assert inverse_recs[0].ticker == "SH"
        assert inverse_recs[0].suggested_weight == 0.10
        assert inverse_recs[0].suggested_amount == 10000.0

    def test_evaluate_hedging_unwind(self, hedging_service):
        """Verify unwinding of inverse hedge when volatility returns to normal."""
        portfolio = {
            "total_nlv": 100000.0,
            "cash_balance": 20000.0,
            "positions": [
                {"symbol": "SH", "market_value": 10000.0, "beta": -1.0, "unrealized_pnl_pct": 0.05},
                {"symbol": "AAPL", "market_value": 70000.0, "beta": 1.0, "unrealized_pnl_pct": 0.15},
            ],
        }
        eval_result = hedging_service.evaluate_hedging(
            portfolio=portfolio,
            vix=18.0,
            vix_z_score=0.4,
        )
        assert eval_result.is_hedging_active is False
        assert eval_result.severity == HedgingSeverity.NORMAL
        unwind_recs = [r for r in eval_result.recommendations if r.action == HedgingActionType.UNWIND_HEDGE]
        assert len(unwind_recs) == 1
        assert unwind_recs[0].ticker == "SH"
        assert unwind_recs[0].suggested_amount == 10000.0


class TestMacroVolatilityHedgeContract:
    def test_contract_properties_and_blindspots(self):
        """Verify strategy contract interface, safety control, and regime subscription."""
        contract = MacroVolatilityHedgeContract()
        assert contract.strategy_id == "macro_volatility_hedge"
        assert contract.is_safety_control() is True
        assert MarketRegimeType.VOLATILITY_EXTREME in contract.subscribed_regimes
        # CRITICAL: Must NOT subscribe to LIQUIDITY_SHOCK to avoid breaking cognitive blindspot test
        assert MarketRegimeType.LIQUIDITY_SHOCK not in contract.subscribed_regimes

    def test_evaluate_entry_and_exit(self):
        """Verify evaluate_entry and evaluate_exit lifecycle."""
        contract = MacroVolatilityHedgeContract()

        # Normal condition -> evaluate_entry returns None
        entry_normal = contract.evaluate_entry({"vix": 18.0, "vix_z_score": 0.5})
        assert entry_normal is None

        # Extreme shock -> evaluate_entry returns plan
        entry_shock = contract.evaluate_entry({
            "vix": 42.0,
            "vix_z_score": 3.0,
            "portfolio": {"total_nlv": 100000.0, "cash_balance": 5000.0, "positions": []},
        })
        assert entry_shock is not None
        assert entry_shock.stage in (1, 2)
        assert entry_shock.target_leverage == 1
        assert "宏觀波動率警戒" in entry_shock.reason

        # Return to normal -> evaluate_exit triggers SELL
        exit_plan = contract.evaluate_exit(
            position={"symbol": "SH", "market_value": 5000.0},
            market_context={"vix": 18.0, "vix_z_score": 0.2},
        )
        assert exit_plan is not None
        assert exit_plan.action == "SELL"
        assert exit_plan.stage == 0


class TestSentinelMacroHedgeIntegration:
    @pytest.mark.asyncio
    async def test_sentinel_macro_shifts_triggers_hedging_plan(self):
        """Verify SentinelService._check_macro_shifts triggers macro_volatility_hedge plan."""
        from src.services.sentinel_service import SentinelService
        from unittest.mock import patch

        mock_market = MagicMock()
        mock_market.get_macro_data.return_value = {
            "economics": {"10Y2Y_Spread": {"value": -0.65}},
            "market_indicators": {"^VIX": 42.5},
        }

        with patch("src.services.sentinel_service.AlchemySentinelRepository"), \
             patch("src.services.sentinel_service.SettingsService") as MockSettings, \
             patch("src.infrastructure.tasks.run_strategy_evolution.delay"):
            MockSettings.return_value.get_setting.return_value = 30.0
            sentinel = SentinelService(
                user_id="test_user",
                market_service=mock_market,
            )
            sentinel.thresholds = {"vix_extreme": 40.0, "vix_high": 25.0}
            sentinel.current_vix = 42.5
            sentinel.current_vix_z_score = 3.2

            triggers = await sentinel._check_macro_shifts()
            macro_hedge_triggers = [t for t in triggers if t.get("strategy_name") == "macro_volatility_hedge"]
            assert len(macro_hedge_triggers) >= 1
            assert "跨市場波動率體制自動避險" in macro_hedge_triggers[0]["text"]
            assert macro_hedge_triggers[0]["priority"] == 1

    @pytest.mark.asyncio
    async def test_sentinel_risk_consistency_dynamic_cash_scaling(self):
        """Verify SentinelService._check_risk_consistency scales cash target under macro hedging."""
        from src.services.sentinel_service import SentinelService
        from unittest.mock import patch, MagicMock

        mock_snapshot = MagicMock()
        mock_snapshot.to_dict.return_value = {
            "total_nlv": 100000.0,
            "cash_balance": 10000.0,  # 10% actual cash
            "leverage_ratio": 1.0,
            "positions": [],
        }

        with patch("src.services.sentinel_service.AlchemySentinelRepository"), \
             patch("src.services.sentinel_service.SettingsService") as MockSettings, \
             patch("src.services.fred_service.FredService"):
            MockSettings.return_value.get_setting.side_effect = lambda k, default=None, user_id=None: {
                "target_cash_ratio": 0.10,
                "risk_profile": "Balanced",
                "enable_macro_volatility_hedging": True,
                "macro_hedge_vix_threshold": 30.0,
                "macro_hedge_target_cash_ratio": 0.25,
            }.get(k, default)

            sentinel = SentinelService(user_id="test_user")
            sentinel.current_vix = 35.0
            sentinel.current_vix_z_score = 2.8
            sentinel._check_vix_anomaly = MagicMock(return_value=[{"text": "🔴 VIX Spike: 35.0 > 28.0"}])
            sentinel.snapshot_repo.get_latest_by_user = MagicMock(return_value=mock_snapshot)

            triggers = await sentinel._check_risk_consistency()
            cash_triggers = [t for t in triggers if t.get("type") == "cash_management" and "cash_ratio_low" in t.get("id", "")]
            assert len(cash_triggers) >= 1
            assert "Dynamic Cash Alert" in cash_triggers[0]["text"]


