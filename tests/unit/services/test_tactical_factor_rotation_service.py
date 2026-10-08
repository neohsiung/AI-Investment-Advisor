"""
Unit Tests for Tactical Factor Rotation & Liquidity Premium Service
===================================================================
驗證多因子流動性溢價與智能波段換倉服務之週期判定、流動性因子度量、
候選池綜合評分、防守現金注入、汰弱換強換倉與策略契約進出場接口。
"""
from unittest.mock import MagicMock
import pytest

from src.domain.strategy_contract import MarketRegimeType
from src.services.tactical_factor_rotation_service import (
    LiquidityFactorMetrics,
    TacticalAssetScore,
    TacticalFactorRotationContract,
    TacticalFactorRotationService,
    TacticalMarketPhase,
    TacticalRotationPlan,
)


class TestTacticalFactorRotationService:
    @pytest.fixture
    def mock_settings_service(self):
        settings = MagicMock()
        config_map = {
            "enable_tactical_factor_rotation": True,
            "factor_liquidity_premium_weight": 0.35,
            "tactical_rotation_min_edge_pct": 8.0,
            "tactical_rotation_max_swaps_per_tick": 2,
            "enable_rebound_cash_reinvestment": True,
            "target_cash_ratio": 0.10,
            "max_single_position_pct": 0.20,
        }
        settings.get_setting.side_effect = lambda k, default=None, user_id=None: config_map.get(k, default)
        return settings

    @pytest.fixture
    def mock_winner_service(self):
        service = MagicMock()
        service.get_certified_winners.return_value = [{"symbol": "NVDA"}]
        return service

    @pytest.fixture
    def rotation_service(self, mock_settings_service, mock_winner_service):
        return TacticalFactorRotationService(
            user_id="test_user",
            settings_service=mock_settings_service,
            winner_service=mock_winner_service,
        )

    def test_determine_market_phase(self, rotation_service):
        """Verify market phase determination across different regimes."""
        # 1. EARLY_REBOUND via regime_hint
        phase, reason = rotation_service.determine_market_phase(
            vix=26.0, vix_z_score=1.2, regime_hint="VOLATILITY_PIVOT"
        )
        assert phase == TacticalMarketPhase.EARLY_REBOUND
        assert "拐點" in reason

        # 2. EARLY_REBOUND via VIX trajectory (22 <= VIX <= 35 and Z < 1.5)
        phase, _ = rotation_service.determine_market_phase(vix=25.0, vix_z_score=0.9)
        assert phase == TacticalMarketPhase.EARLY_REBOUND

        # 3. DEFENSIVE_CONSOLIDATION (VIX >= 30 or extreme Z >= 2.5)
        phase, _ = rotation_service.determine_market_phase(vix=32.0, vix_z_score=2.6)
        assert phase == TacticalMarketPhase.DEFENSIVE_CONSOLIDATION

        # 4. LATE_CYCLE_VALUE (inverted yield spread and calm VIX)
        phase, _ = rotation_service.determine_market_phase(
            vix=18.0, vix_z_score=0.2, yield_spread=-0.45
        )
        assert phase == TacticalMarketPhase.LATE_CYCLE_VALUE

        # 5. BULL_ACCELERATION (SPY above SMA200 and low VIX)
        phase, _ = rotation_service.determine_market_phase(
            vix=16.0, vix_z_score=-0.5, spy_price=550.0, spy_sma200=500.0
        )
        assert phase == TacticalMarketPhase.BULL_ACCELERATION

    def test_get_phase_factor_weights(self, rotation_service):
        """Verify factor weight allocation and normalization."""
        for phase in TacticalMarketPhase:
            weights = rotation_service.get_phase_factor_weights(phase)
            assert isinstance(weights, dict)
            assert "liquidity_premium" in weights
            # Sum of weights should be approximately 1.0
            total_w = sum(weights.values())
            assert abs(total_w - 1.0) < 0.05

    def test_compute_liquidity_premium_metrics(self, rotation_service):
        """Verify calculation of volume expansion and cross-sectional percentile score."""
        ticker_metrics = {
            "NVDA": {"adv_5d": 3000.0, "adv_20d": 1500.0, "turnover_ratio": 0.05, "amihud_ratio": 0.0001},
            "AAPL": {"adv_5d": 1000.0, "adv_20d": 1000.0, "turnover_ratio": 0.02, "amihud_ratio": 0.0002},
            "INTC": {"adv_5d": 500.0, "adv_20d": 1000.0, "turnover_ratio": 0.01, "amihud_ratio": 0.0005},
        }
        res = rotation_service.compute_liquidity_premium_metrics(ticker_metrics)

        assert "NVDA" in res
        assert "AAPL" in res
        assert "INTC" in res

        # NVDA has 2.0 expansion, AAPL has 1.0, INTC has 0.5
        assert res["NVDA"].volume_expansion_ratio == 2.0
        assert res["AAPL"].volume_expansion_ratio == 1.0
        assert res["INTC"].volume_expansion_ratio == 0.5

        # NVDA should have highest liquidity_premium_score, INTC lowest
        assert res["NVDA"].liquidity_premium_score > res["AAPL"].liquidity_premium_score
        assert res["AAPL"].liquidity_premium_score > res["INTC"].liquidity_premium_score

    def test_score_candidate_universe(self, rotation_service):
        """Verify multi-factor candidate scoring and ranking."""
        candidate_data = {
            "NVDA": {
                "momentum": 0.90,
                "smart_money": 0.85,
                "adv_5d": 2000.0,
                "adv_20d": 1000.0,
                "quality": 0.80,
                "value": 0.40,
                "beta": 1.6,
            },
            "MSFT": {
                "momentum": 0.70,
                "smart_money": 0.75,
                "adv_5d": 1000.0,
                "adv_20d": 1000.0,
                "quality": 0.95,
                "value": 0.60,
                "beta": 1.1,
            },
            "INTC": {
                "momentum": 0.20,
                "smart_money": 0.25,
                "adv_5d": 500.0,
                "adv_20d": 1000.0,
                "quality": 0.40,
                "value": 0.70,
                "beta": 0.9,
            },
        }
        scores = rotation_service.score_candidate_universe(
            candidate_data, TacticalMarketPhase.EARLY_REBOUND
        )

        assert len(scores) == 3
        assert scores[0].ticker == "NVDA"
        assert scores[0].rank == 1
        assert scores[0].alpha_elasticity_score > scores[1].alpha_elasticity_score
        assert scores[2].ticker == "INTC"

    def test_direct_cash_deployment_in_early_rebound(self, rotation_service):
        """Verify deployment of excess defensive cash into top alpha leaders."""
        portfolio = {
            "total_nlv": 100000.0,
            "cash_balance": 30000.0,  # Base target 10% = 10,000, excess = 20,000
            "positions": [
                {"symbol": "MSFT", "market_value": 70000.0, "quantity": 175},
            ],
        }
        candidate_data = {
            "NVDA": {
                "momentum": 0.95,
                "smart_money": 0.90,
                "adv_5d": 3000.0,
                "adv_20d": 1500.0,
                "quality": 0.85,
                "value": 0.40,
                "beta": 1.8,
            },
            "TSM": {
                "momentum": 0.90,
                "smart_money": 0.85,
                "adv_5d": 2500.0,
                "adv_20d": 1300.0,
                "quality": 0.90,
                "value": 0.50,
                "beta": 1.4,
            },
        }

        plan = rotation_service.evaluate_rotation_plan(
            portfolio=portfolio,
            candidate_data=candidate_data,
            vix=26.0,
            vix_z_score=1.0,  # Early rebound
        )

        assert plan.phase == TacticalMarketPhase.EARLY_REBOUND
        buy_orders = [o for o in plan.rebalance_orders if o["action"] == "BUY"]
        assert len(buy_orders) >= 1
        assert any(o["ticker"] == "NVDA" for o in buy_orders)
        assert all(o["strategy_name"] == "tactical_factor_rotation" for o in buy_orders)

    def test_friction_aware_swaps_and_winner_protection(self, rotation_service):
        """Verify swapping out underperforming holdings into top candidates while protecting certified winners."""
        # NVDA is certified winner via mock_winner_service, INTC is lagging holding
        portfolio = {
            "total_nlv": 100000.0,
            "cash_balance": 10000.0,
            "positions": [
                {"symbol": "NVDA", "market_value": 20000.0, "quantity": 160},
                {"symbol": "INTC", "market_value": 15000.0, "quantity": 500},
                {"symbol": "MSFT", "market_value": 55000.0, "quantity": 140},
            ],
        }
        candidate_data = {
            "NVDA": {"momentum": 0.95, "smart_money": 0.90, "adv_5d": 3000.0, "adv_20d": 1500.0, "quality": 0.85},
            "AVGO": {"momentum": 0.92, "smart_money": 0.88, "adv_5d": 2800.0, "adv_20d": 1400.0, "quality": 0.88},
            "INTC": {"momentum": 0.15, "smart_money": 0.20, "adv_5d": 400.0, "adv_20d": 1000.0, "quality": 0.30},
            "MSFT": {"momentum": 0.70, "smart_money": 0.70, "adv_5d": 1000.0, "adv_20d": 1000.0, "quality": 0.85},
        }

        plan = rotation_service.evaluate_rotation_plan(
            portfolio=portfolio,
            candidate_data=candidate_data,
            vix=18.0,
            vix_z_score=0.0,
            spy_price=560.0,
            spy_sma200=500.0,  # Bull acceleration
        )

        assert plan.phase == TacticalMarketPhase.BULL_ACCELERATION
        assert len(plan.swaps_approved) >= 1

        swap = plan.swaps_approved[0]
        # INTC should be swapped out for AVGO (NVDA is protected certified winner)
        assert swap["sell_ticker"] == "INTC"
        assert swap["buy_ticker"] == "AVGO"
        assert swap["sell_ticker"] != "NVDA"

        # Check rebalance orders reflect the swap
        sell_orders = [o for o in plan.rebalance_orders if o["action"] == "SELL"]
        buy_orders = [o for o in plan.rebalance_orders if o["action"] == "BUY"]

        assert any(o["ticker"] == "INTC" for o in sell_orders)
        assert any(o["ticker"] == "AVGO" for o in buy_orders)

    def test_disabled_rotation_plan(self, rotation_service, mock_settings_service):
        """When enable_tactical_factor_rotation is False, no rebalances or swaps are generated."""
        mock_settings_service.get_setting.side_effect = lambda k, default=None, user_id=None: (
            False if k == "enable_tactical_factor_rotation" else default
        )
        plan = rotation_service.evaluate_rotation_plan(
            portfolio={"total_nlv": 50000.0, "cash_balance": 10000.0, "positions": []},
            candidate_data={"NVDA": {"momentum": 0.9}},
            vix=20.0,
        )
        assert len(plan.rebalance_orders) == 0
        assert len(plan.swaps_approved) == 0
        assert "未啟用" in plan.phase_rationale

    def test_max_swaps_per_tick_enforcement(self, rotation_service, mock_settings_service):
        """Ensure swap executions do not exceed tactical_rotation_max_swaps_per_tick limit."""
        mock_settings_service.get_setting.side_effect = lambda k, default=None, user_id=None: (
            1 if k == "tactical_rotation_max_swaps_per_tick" else default
        )
        portfolio = {
            "total_nlv": 100000.0,
            "cash_balance": 10000.0,
            "positions": [
                {"symbol": "HOLD_LOW1", "market_value": 15000.0},
                {"symbol": "HOLD_LOW2", "market_value": 15000.0},
            ],
        }
        candidate_data = {
            "TOP_CAND1": {"momentum": 0.95, "smart_money": 0.90, "adv_5d": 3000.0, "adv_20d": 1500.0, "quality": 0.85},
            "TOP_CAND2": {"momentum": 0.92, "smart_money": 0.88, "adv_5d": 2800.0, "adv_20d": 1400.0, "quality": 0.88},
            "HOLD_LOW1": {"momentum": 0.10, "smart_money": 0.10, "adv_5d": 300.0, "adv_20d": 1000.0, "quality": 0.20},
            "HOLD_LOW2": {"momentum": 0.15, "smart_money": 0.15, "adv_5d": 350.0, "adv_20d": 1000.0, "quality": 0.25},
        }

        plan = rotation_service.evaluate_rotation_plan(
            portfolio=portfolio,
            candidate_data=candidate_data,
            vix=18.0,
            vix_z_score=0.0,
            spy_price=560.0,
            spy_sma200=500.0,
        )
        assert len(plan.swaps_approved) == 1

    def test_custom_liquidity_premium_weight(self, rotation_service, mock_settings_service):
        """Verify custom factor_liquidity_premium_weight scales factor weight allocation."""
        mock_settings_service.get_setting.side_effect = lambda k, default=None, user_id=None: (
            0.50 if k == "factor_liquidity_premium_weight" else default
        )
        weights = rotation_service.get_phase_factor_weights(TacticalMarketPhase.EARLY_REBOUND)
        assert weights["liquidity_premium"] == 0.50
        assert abs(sum(weights.values()) - 1.0) < 0.05


class TestTacticalFactorRotationContract:
    @pytest.fixture
    def contract(self):
        return TacticalFactorRotationContract()

    def test_contract_metadata_and_safety_flag(self, contract):
        """Verify contract identification, subscribed regimes, and safety control status."""
        assert contract.strategy_id == "tactical_factor_rotation"
        assert contract.is_safety_control() is False
        assert MarketRegimeType.TREND_ACCELERATION in contract.subscribed_regimes
        assert MarketRegimeType.VOLATILITY_PIVOT in contract.subscribed_regimes
        assert MarketRegimeType.NORMAL in contract.subscribed_regimes
        # CRITICAL: LIQUIDITY_SHOCK must NOT be subscribed to protect cognitive blindspot detection
        assert MarketRegimeType.LIQUIDITY_SHOCK not in contract.subscribed_regimes

    def test_evaluate_entry(self, contract):
        """Verify entry plan generation when rotation opportunities exist."""
        market_context = {
            "vix": 26.0,
            "vix_z_score": 1.0,
            "portfolio": {
                "total_nlv": 100000.0,
                "cash_balance": 25000.0,
                "positions": [],
            },
            "candidate_data": {
                "NVDA": {
                    "momentum": 0.95,
                    "smart_money": 0.90,
                    "adv_5d": 3000.0,
                    "adv_20d": 1500.0,
                    "quality": 0.85,
                    "value": 0.40,
                }
            },
        }
        plan = contract.evaluate_entry(market_context)
        assert plan is not None
        assert plan.action == "BUY"
        assert plan.is_trailing_stop_loss is True
        assert "波段輪動建倉" in plan.reason

    def test_evaluate_exit(self, contract):
        """Verify exit plan generation for lagging assets during rotation."""
        position = {"symbol": "INTC", "quantity": 100}
        plan = contract.evaluate_exit(position, {"underperforming_tickers": ["INTC"]})
        assert plan is not None
        assert plan.action == "PARTIAL_EXIT"
        assert "INTC" in plan.reason
        assert "汰換" in plan.reason

        # Position not lagging
        no_exit = contract.evaluate_exit({"symbol": "NVDA"}, {"underperforming_tickers": ["INTC"]})
        assert no_exit is None
