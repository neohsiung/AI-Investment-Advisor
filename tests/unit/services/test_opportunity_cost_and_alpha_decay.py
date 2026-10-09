"""
Unit tests for M3: Dynamic Opportunity Cost & Alpha Decay Swapping.
測試非線性換庫機會成本門檻與持倉 Alpha 鈍化衰減機制。
"""
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, AsyncMock, patch
import pytest

from src.services.opportunity_cost_service import OpportunityCostService, SwapAssessment
from src.services.alpha_decay_service import AlphaDecayService, AlphaDecayAssessment
from src.services.ticker_universe_service import TickerUniverseService
from src.services.confidence_rebalance_service import ConfidenceRebalanceService


class TestOpportunityCostService:

    def test_roundtrip_friction_calculation(self):
        """Verify 2-way round-trip trading friction calculation."""
        service = OpportunityCostService(user_id="test-user")
        # Default: 2 * (0.0010 + 0.0005) = 0.0030 (0.30%)
        friction = service.calculate_roundtrip_friction()
        assert friction == 0.0030

        # Custom values
        custom_friction = service.calculate_roundtrip_friction(slippage_pct=0.002, commission_pct=0.001)
        assert custom_friction == 0.0060

    def test_opportunity_cost_hurdle_calculation(self):
        """Verify non-linear hurdle: Multiplier * Friction + HurdleRate."""
        mock_settings = MagicMock()
        mock_settings.get_setting.side_effect = lambda key, default=None: {
            "rotation_friction_multiplier": 2.5,
            "rotation_hurdle_rate": 0.010,
        }.get(key, default)

        service = OpportunityCostService(user_id="test-user", settings_service=mock_settings)
        # 2.5 * 0.0030 + 0.010 = 0.0075 + 0.010 = 0.0175 (1.75%)
        hurdle = service.calculate_opportunity_cost_hurdle()
        assert hurdle == 0.0175

    def test_evaluate_swap_insufficient_edge_rejected(self):
        """Marginal score advantage (< hurdle) is rejected to prevent fee churn."""
        mock_settings = MagicMock()
        mock_settings.get_setting.side_effect = lambda key, default=None: {
            "rotation_friction_multiplier": 2.5,
            "rotation_hurdle_rate": 0.010,
        }.get(key, default)

        service = OpportunityCostService(user_id="test-user", settings_service=mock_settings)

        # Selling asset with score 7.5 (0.75), Candidate with score 8.0 (0.80)
        # Delta = 0.05 -> expected_edge = 0.05 * 0.10 = 0.0050 (0.50%) < 1.75% hurdle
        assessment = service.evaluate_swap(
            selling_ticker="HOLDING_A",
            buying_ticker="CANDIDATE_B",
            sell_confidence=7.5,
            buy_confidence=8.0,
        )

        assert assessment.is_approved is False
        assert assessment.expected_edge < assessment.hurdle
        assert "未達非線性機會成本門檻" in assessment.reason
        assert "抑制無謂換手" in assessment.reason

    def test_evaluate_swap_significant_edge_approved(self):
        """Significant score advantage (>= hurdle) is approved."""
        mock_settings = MagicMock()
        mock_settings.get_setting.side_effect = lambda key, default=None: {
            "rotation_friction_multiplier": 2.5,
            "rotation_hurdle_rate": 0.010,
        }.get(key, default)

        service = OpportunityCostService(user_id="test-user", settings_service=mock_settings)

        # Selling asset with score 5.5, Candidate with score 9.5
        # Delta = 0.40 -> expected_edge = 0.40 * 0.10 = 0.0400 (4.0%) >= 1.75% hurdle
        assessment = service.evaluate_swap(
            selling_ticker="HOLDING_A",
            buying_ticker="CANDIDATE_B",
            sell_confidence=5.5,
            buy_confidence=9.5,
        )

        assert assessment.is_approved is True
        assert assessment.expected_edge >= assessment.hurdle
        assert "顯著超越非線性機會成本門檻" in assessment.reason
        assert "核准置換" in assessment.reason

    def test_evaluate_swap_raw_delta_exceeds_but_net_delta_below_hurdle_rejected(self):
        """
        Verify bugfix: raw_delta >= hurdle (e.g. 2.10 >= 2.00)
        but net_delta < hurdle (e.g. 1.81 < 2.00 after subtracting friction hurdle)
        must be rejected (should_swap=False) to prevent churn from eroding edge.
        """
        service = OpportunityCostService(user_id="test-user", min_score_delta=2.0)
        # holding score 5.0, candidate score 7.1 -> raw_delta = 2.10 >= 2.00
        # net_delta = raw_delta - friction_hurdle_score (~0.30) = 1.80 < 2.00
        # With raw_delta >= hurdle (2.10 >= 2.0) but net_delta < hurdle (1.80 < 2.0),
        # the swap must be rejected to prevent churn from eroding the edge.
        assessment = service.evaluate_swap(
            holding_ticker="TSM",
            candidate_ticker="AMD",
            holding_score=5.0,
            candidate_score=7.1,
        )
        assert assessment.should_swap is False
        assert "未達非線性機會成本門檻" in assessment.reason
        assert "抑制無謂換手" in assessment.reason

    def test_evaluate_swap_with_expected_returns(self):
        """Test expected return deltas scaled across 60-day horizon."""
        mock_settings = MagicMock()
        mock_settings.get_setting.side_effect = lambda key, default=None: {
            "rotation_friction_multiplier": 2.5,
            "rotation_hurdle_rate": 0.010,
        }.get(key, default)

        service = OpportunityCostService(user_id="test-user", settings_service=mock_settings)

        # Candidate expected return 22%, Holding expected return 6%
        # Delta return = 16% annualized -> over 60 days (60/252 = 0.238): ~3.8% return edge
        assessment = service.evaluate_swap(
            selling_ticker="HOLDING_A",
            buying_ticker="CANDIDATE_B",
            sell_expected_return=0.06,
            buy_expected_return=0.22,
            sell_confidence=0.6,
            buy_confidence=0.9,
            horizon_days=60,
        )

        assert assessment.is_approved is True
        assert assessment.expected_edge >= 0.02

    def test_evaluate_swap_exemptions(self):
        """Evicted dead capital pruning and risk trims bypass hurdle unconditionally."""
        service = OpportunityCostService(user_id="test-user")

        prune_eval = service.evaluate_swap(
            selling_ticker="DEAD_LOT",
            buying_ticker="CANDIDATE",
            is_pruning=True,
        )
        assert prune_eval.is_approved is True
        assert "淘汰標的與死資本清倉" in prune_eval.reason

        risk_eval = service.evaluate_swap(
            selling_ticker="OVERWEIGHT_LOT",
            buying_ticker="CANDIDATE",
            is_risk_trim=True,
        )
        assert risk_eval.is_approved is True
        assert "剛性風控平倉" in risk_eval.reason

    def test_filter_rebalance_trades_selective(self):
        """filter_rebalance_trades filters tactical trims and swaps with insufficient edge."""
        service = OpportunityCostService(user_id="test-user")

        sells = [
            {"ticker": "EVICTED", "delta_amount": -1000.0, "is_pruning": True, "confidence": 5.0},
            {"ticker": "TACTICAL_WEAK", "delta_amount": -500.0, "is_tactical_trim": True, "confidence": 8.0},
            {"ticker": "TACTICAL_STRONG", "delta_amount": -500.0, "is_tactical_trim": True, "confidence": 5.0},
        ]
        buys = [
            {"ticker": "TOP_BUY", "delta_amount": 2000.0, "confidence": 8.5},
        ]

        result = service.filter_rebalance_trades(sells=sells, buys=buys, total_portfolio_value=10000.0)
        approved_tickers = [s["ticker"] for s in result["approved_sells"]]
        suppressed_tickers = [s["ticker"] for s in result["suppressed_sells"]]

        assert "EVICTED" in approved_tickers
        assert "TACTICAL_STRONG" in approved_tickers  # 8.5 vs 5.0 -> edge approved
        assert "TACTICAL_WEAK" in suppressed_tickers   # 8.5 vs 8.0 -> delta 0.5 < hurdle -> suppressed
        assert result["suppressed_sells"][0]["action"] == "HOLD_INSUFFICIENT_EDGE"


class TestAlphaDecayService:

    def test_calculate_holding_days(self):
        """Verify holding days calculation from open_date."""
        service = AlphaDecayService(user_id="test-user")
        now = datetime(2026, 10, 1, 12, 0, 0, tzinfo=timezone.utc)
        open_date = datetime(2026, 9, 11, 12, 0, 0, tzinfo=timezone.utc)

        days = service.calculate_holding_days(open_date, now=now)
        assert days == 20

        # None open date
        assert service.calculate_holding_days(None) == 0

    def test_grace_period_no_decay(self):
        """Positions held <= 20 days receive no decay."""
        service = AlphaDecayService(user_id="test-user")
        assessment = service.evaluate_holding_decay(
            ticker="NVDA",
            holding_days=15,
            current_price=120.0,
            sma_20=115.0,
            rsi=55.0,
        )

        assert assessment.has_decay is False
        assert assessment.decay_factor == 1.0
        assert "未達衰減考覈門檻" in assessment.reason

    def test_winner_compounding_protection_no_decay(self):
        """Long-tenure position (> 20d) with healthy momentum and positive alpha is 100% protected."""
        service = AlphaDecayService(user_id="test-user")
        assessment = service.evaluate_holding_decay(
            ticker="MSFT",
            holding_days=45,
            current_price=510.0,
            sma_20=495.0,
            rsi=62.0,
            macd_status="bullish",
            holding_return_pct=0.15,
            benchmark_return_pct=0.05,
            is_long_term_winner=True,
        )

        assert assessment.has_decay is False
        assert assessment.decay_factor == 1.0
        assert "全額保護長線複利" in assessment.reason

    def test_stagnant_holding_exponential_decay(self):
        """Position held > 20d with broken 20MA and negative relative alpha incurs exponential decay."""
        service = AlphaDecayService(user_id="test-user")
        # 40 days held -> 20 excess days beyond start (20d)
        # exp(-0.035 * 20) = exp(-0.70) = ~0.4966
        assessment = service.evaluate_holding_decay(
            ticker="STALE_STOCK",
            holding_days=40,
            current_price=90.0,
            sma_20=100.0,  # below 20MA
            rsi=38.0,      # weak momentum
            macd_status="bearish",
            holding_return_pct=-0.05,
            benchmark_return_pct=0.08,
        )

        assert assessment.has_decay is True
        assert 0.40 <= assessment.decay_factor < 0.60
        assert "動能鈍化" in assessment.reason
        assert "Alpha 衰減機制" in assessment.reason

    def test_holding_decay_floor_enforcement(self):
        """Extreme stagnation beyond 100 days never decays below floor (0.40)."""
        service = AlphaDecayService(user_id="test-user")
        assessment = service.evaluate_holding_decay(
            ticker="VERY_STALE",
            holding_days=150,
            current_price=50.0,
            sma_20=80.0,
            rsi=30.0,
            macd_status="bearish",
            holding_return_pct=-0.20,
            benchmark_return_pct=0.10,
        )

        assert assessment.decay_factor == 0.40

    def test_apply_decay_to_confidence(self):
        """Confidence score is safely decayed with a floor."""
        service = AlphaDecayService(user_id="test-user")
        # 0-1 scale
        decayed = service.apply_decay_to_confidence(0.80, 0.50)
        assert decayed == 0.40

        # 0-10 scale
        decayed_10 = service.apply_decay_to_confidence(8.0, 0.50)
        assert decayed_10 == 4.0


class TestPipelineIntegration:

    def test_optimize_allocations_applies_alpha_decay(self):
        """optimize_allocations incorporates AlphaDecayService when current_holdings is provided."""
        svc = TickerUniverseService(user_id="test-user")

        # Mock repo to return 2 active tickers: AAPL (fresh) and STALE (held 50 days, stagnant)
        svc.repo.get_all = MagicMock(return_value=[
            {"ticker": "AAPL", "sector": "Tech", "status": "active"},
            {"ticker": "STALE", "sector": "Tech", "status": "active"},
        ])
        svc.repo.upsert_target = MagicMock(return_value=True)
        svc.repo.add_log = MagicMock()
        svc.repo.get_research = MagicMock(side_effect=lambda uid, t, limit=5: [
            {"confidence_score": 0.80, "expected_return": 0.10}
        ])
        svc.settings_service.get_setting = MagicMock(side_effect=lambda key, default=None: {
            "alloc_min_position": 0.03,
            "alloc_max_position": 0.70,
            "alloc_sector_cap": 0.80,
            "alloc_cluster_cap": 0.80,
            "alloc_correlation_cluster_threshold": 0.70,
            "alloc_target_volatility": 0.35,
            "alloc_target_beta": 1.50,
            "alloc_target_sum": 0.95,
            "alloc_max_holdings": 10,
            "holding_decay_start_days": 20,
            "holding_decay_rate": 0.035,
            "holding_decay_floor": 0.40,
        }.get(key, default))
        svc.calculate_ticker_returns = MagicMock(return_value=[0.01] * 60)
        svc.calculate_ticker_volatility = MagicMock(return_value=0.20)
        svc.calculate_ticker_beta = MagicMock(return_value=1.0)
        svc.build_correlation_clusters = MagicMock(return_value=({}, [["AAPL"], ["STALE"]]))
        svc.apply_cluster_caps = MagicMock(side_effect=lambda w, c, cluster_cap: w)

        # Baseline without decay: equal scores -> equal target weights
        res_baseline = svc.optimize_allocations()
        assert res_baseline["success"]
        t_base = {t["ticker"]: t["target_weight"] for t in res_baseline["targets"]}
        assert abs(t_base["AAPL"] - t_base["STALE"]) < 0.05

        # With current holdings: STALE held 50 days, broken 20MA, negative alpha
        current_holdings = {
            "STALE": {
                "holding_days": 50,
                "current_price": 85.0,
                "sma_20": 100.0,
                "rsi": 35.0,
                "macd": "bearish",
                "return_since_entry": -0.10,
                "benchmark_return_pct": 0.10,
            }
        }
        res_decayed = svc.optimize_allocations(current_holdings=current_holdings)
        assert res_decayed["success"]
        t_decay = {t["ticker"]: t["target_weight"] for t in res_decayed["targets"]}

        # STALE target weight should be significantly lower than AAPL
        assert t_decay["STALE"] < t_decay["AAPL"]
        assert "STALE" in res_decayed.get("decay_factors", {})
        assert res_decayed["decay_factors"]["STALE"] < 1.0

    @pytest.mark.asyncio
    async def test_rebalance_plan_reclaims_with_opportunity_cost(self):
        """reclaim_capital_for_buy uses OpportunityCostService to reject marginal edge reclaims."""
        svc = ConfidenceRebalanceService(user_id="test-user")

        # Mock current portfolio with 1 active stock and $0 cash
        svc._get_current_weights = AsyncMock(return_value={
            "weights": {"MARGINAL_STOCK": 20.0},
            "cash_weight": 0.0,
            "total_value": 10000.0,
        })
        svc.ticker_service.get_targets = MagicMock(return_value=[
            {"ticker": "MARGINAL_STOCK", "target_weight": 0.20}
        ])
        svc.ticker_service.repo.get_research = MagicMock(return_value=[
            {"confidence_score": 8.0}
        ])

        # Candidate with score 8.2 (only 0.2 gap vs 8.0) -> fails opportunity cost hurdle
        res = await svc.reclaim_capital_for_buy(
            candidate_ticker="NEW_CANDIDATE",
            target_amount=1000.0,
            candidate_score=8.2,
            execute=False,
        )

        assert res["reclaimed_amount"] == 0.0
        assert len(res["sells"]) == 0
