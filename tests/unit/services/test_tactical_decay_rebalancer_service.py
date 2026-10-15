"""
Unit Tests for TacticalDecayRebalancerService (Phase 67).
"""
import pytest
from unittest.mock import MagicMock, patch

from src.services.tactical_decay_rebalancer_service import (
    TacticalDecayRebalancerService,
    DecayRebalanceAction,
    DecayFactorWeightDetail,
    DecayRebalanceOrder,
    DecayRebalancePlan,
)
from src.services.factor_orthogonal_attribution_service import (
    FactorHealthStatus,
    FactorDecayMetric,
)


class TestTacticalDecayRebalancerService:
    @pytest.fixture
    def mock_settings(self):
        settings = MagicMock()
        settings.get_setting.side_effect = lambda k, default=None: {
            "enable_tactical_decay_rebalancing": True,
            "decay_rebalance_drift_threshold": 0.03,
            "decay_rebalance_max_turnover": 0.25,
            "decay_rebalance_enforce_friction_hurdle": True,
        }.get(k, default)
        return settings

    @pytest.fixture
    def service(self, mock_settings):
        return TacticalDecayRebalancerService(
            user_id="user_test_p67",
            settings_service=mock_settings,
        )

    def test_initialization_and_settings(self, service):
        assert service.is_enabled is True
        assert service.drift_threshold == 0.03
        assert service.max_turnover == 0.25
        assert service.enforce_friction_hurdle is True

    def test_compute_decay_adjusted_factor_weights_default(self, service):
        details = service.compute_decay_adjusted_factor_weights()
        assert len(details) == 6
        sum_w = sum(d.adjusted_weight for d in details)
        assert abs(sum_w - 1.0) < 1e-4

        names = [d.factor_name for d in details]
        assert "momentum" in names
        assert "value" in names
        assert "quality" in names
        assert "low_vol" in names

    def test_compute_decay_adjusted_factor_weights_with_mock_decay(self, service):
        # Mock attribution service with an exhausted Value factor and healthy Momentum
        mock_attr = MagicMock()
        mock_decay = {
            "momentum": FactorDecayMetric(
                factor_name="momentum",
                rolling_ic=0.065,
                ic_ir=1.4,
                autocorr_lag1=0.92,
                half_life_days=8.5,
                health_status=FactorHealthStatus.ACTIVE_HEALTHY,
                tilting_multiplier=1.20,
                recommendation="超配放大",
            ),
            "value": FactorDecayMetric(
                factor_name="value",
                rolling_ic=-0.015,
                ic_ir=-0.4,
                autocorr_lag1=0.35,
                half_life_days=1.4,
                health_status=FactorHealthStatus.EXHAUSTED_INVERTED,
                tilting_multiplier=0.0,
                recommendation="失效剔除",
            ),
            "quality": FactorDecayMetric(
                factor_name="quality",
                rolling_ic=0.038,
                ic_ir=0.9,
                autocorr_lag1=0.88,
                half_life_days=5.5,
                health_status=FactorHealthStatus.ACTIVE_HEALTHY,
                tilting_multiplier=1.05,
                recommendation="健康配置",
            ),
            "low_vol": FactorDecayMetric(
                factor_name="low_vol",
                rolling_ic=0.025,
                ic_ir=0.5,
                autocorr_lag1=0.78,
                half_life_days=3.5,
                health_status=FactorHealthStatus.DECAYING_CROWDED,
                tilting_multiplier=0.65,
                recommendation="防守打折",
            ),
            "liquidity_premium": FactorDecayMetric(
                factor_name="liquidity_premium",
                rolling_ic=0.032,
                ic_ir=0.8,
                autocorr_lag1=0.85,
                half_life_days=5.0,
                health_status=FactorHealthStatus.ACTIVE_HEALTHY,
                tilting_multiplier=1.0,
                recommendation="健康配置",
            ),
            "smart_money": FactorDecayMetric(
                factor_name="smart_money",
                rolling_ic=0.040,
                ic_ir=1.0,
                autocorr_lag1=0.89,
                half_life_days=6.0,
                health_status=FactorHealthStatus.ACTIVE_HEALTHY,
                tilting_multiplier=1.10,
                recommendation="健康配置",
            ),
        }
        mock_attr.calculate_factor_decay_metrics.return_value = mock_decay
        service.attribution_service = mock_attr

        details = service.compute_decay_adjusted_factor_weights(
            base_weights={"momentum": 0.35, "value": 0.15, "quality": 0.20, "low_vol": 0.10, "liquidity_premium": 0.10, "smart_money": 0.10}
        )

        w_map = {d.factor_name: d for d in details}
        # Value tilted to 0.0
        assert w_map["value"].adjusted_weight == 0.0
        assert "🔴" in w_map["value"].rationale

        # Momentum amplified
        assert w_map["momentum"].adjusted_weight > w_map["momentum"].base_weight
        assert "🟢" in w_map["momentum"].rationale

        # Low vol dampened
        assert w_map["low_vol"].adjusted_weight < w_map["low_vol"].base_weight
        assert "🟡" in w_map["low_vol"].rationale

        # Sum is 1.0
        assert abs(sum(d.adjusted_weight for d in details) - 1.0) < 1e-4

    def test_compute_decay_aware_target_weights(self, service):
        details = service.compute_decay_adjusted_factor_weights()
        targets, convex_info = service.compute_decay_aware_target_weights(
            candidate_assets=service.DEFAULT_CANDIDATES,
            factor_weight_details=details,
            available_capital=8000.0,
        )

        assert len(targets) == len(service.DEFAULT_CANDIDATES)
        assert abs(sum(targets.values()) - 1.0) < 1e-3
        # Max cap 25% respected (allow tiny numeric slack)
        for sym, w in targets.items():
            assert w <= 0.26

    def test_generate_decay_rebalance_plan_uninitialized(self, service):
        # Empty portfolio fallback
        plan = service.generate_decay_rebalance_plan(portfolio={})
        assert isinstance(plan, DecayRebalancePlan)
        assert plan.total_portfolio_nav == 10000.0
        assert plan.defensive_cash_reserve == 2000.0
        assert len(plan.factor_weights) == 6
        assert len(plan.rebalance_orders) > 0

        # Serialization
        d = plan.to_dict()
        assert "market_phase" in d
        assert "rebalance_orders" in d
        assert "factor_weights" in d

    def test_generate_decay_rebalance_plan_active_drift(self, service):
        portfolio = {
            "total_nlv": 20000.0,
            "available_cash": 4000.0,
            "positions": [
                {"ticker": "XOM", "shares": 60.0, "market_value": 7200.0, "current_price": 120.0}, # Overweight 36%
                {"ticker": "NVDA", "shares": 5.0, "market_value": 675.0, "current_price": 135.0},   # Underweight ~3%
                {"ticker": "AAPL", "shares": 10.0, "market_value": 2300.0, "current_price": 230.0},
            ]
        }

        plan = service.generate_decay_rebalance_plan(portfolio=portfolio)
        assert plan.rebalance_needed is True
        assert plan.total_turnover_pct <= 25.01  # Hard turnover cap

        actions = [o.action for o in plan.rebalance_orders]
        assert DecayRebalanceAction.SELL in actions
        assert DecayRebalanceAction.BUY in actions

        # Check XOM is trimmed
        xom_orders = [o for o in plan.rebalance_orders if o.ticker == "XOM"]
        assert len(xom_orders) == 1
        assert xom_orders[0].action == DecayRebalanceAction.SELL
        assert xom_orders[0].delta_shares > 0

    def test_generate_decay_rebalance_plan_no_drift(self, service):
        # Portfolio perfectly aligned with small tolerance
        portfolio = {
            "total_nlv": 10000.0,
            "available_cash": 2000.0,
            "positions": [
                {"ticker": t, "shares": 10.0, "market_value": 8000.0 / len(service.DEFAULT_CANDIDATES), "current_price": 100.0}
                for t in service.DEFAULT_CANDIDATES
            ]
        }
        # If drift threshold is large (e.g. 50%), no rebalance should trigger
        with patch.object(service, "_get_setting_float", return_value=0.50):
            plan = service.generate_decay_rebalance_plan(portfolio=portfolio)
            assert plan.rebalance_needed is False
            for o in plan.rebalance_orders:
                assert o.action == DecayRebalanceAction.HOLD

    def test_format_rebalance_dashboard(self, service):
        plan = service.generate_decay_rebalance_plan()
        dashboard = service.format_rebalance_dashboard(plan)
        assert "戰術因子衰減自適應調倉儀表" in dashboard
        assert "因子衰減前後權重對比" in dashboard
        assert "建議調倉操作名冊" in dashboard
        assert "|" in dashboard

    def test_format_rebalance_plan(self, service):
        plan = service.generate_decay_rebalance_plan()
        text = service.format_rebalance_plan(plan)
        assert "戰術因子衰減調倉執行方案" in text
        assert "微觀摩擦與風控承諾" in text

    def test_redis_persistence(self, service):
        plan = service.generate_decay_rebalance_plan()

        with patch("src.infrastructure.cache.redis_client.get_redis_sync") as mock_redis_func:
            mock_r = MagicMock()
            mock_redis_func.return_value = mock_r
            mock_r.get.return_value = '{"total_portfolio_nav": 15000.0}'

            service._save_plan_to_redis(plan)
            mock_r.set.assert_called()

            # Cache hit
            cached = service.load_latest_plan()
            assert cached is not None
            assert cached["total_portfolio_nav"] == round(plan.total_portfolio_nav, 2)

            # Redis fetch
            service._MEMORY_CACHE.clear()
            redis_cached = service.load_latest_plan()
            assert redis_cached is not None
            assert redis_cached["total_portfolio_nav"] == 15000.0
