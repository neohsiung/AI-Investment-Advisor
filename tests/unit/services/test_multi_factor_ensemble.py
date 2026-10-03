"""
Unit Tests for MultiFactorEnsembleService (M6)
"""
from __future__ import annotations

import math
from typing import Any

from src.services.multi_factor_ensemble_service import (
    MultiFactorEnsembleService,
    RawFactorMetrics,
)


class DummySettingsService:
    def __init__(self, settings: dict[str, Any] | None = None):
        self.settings = settings or {}

    def get_setting(self, key: str, default: Any = None) -> Any:
        return self.settings.get(key, default)


class TestMultiFactorEnsembleService:
    def test_regime_weights_adaptation(self):
        """Test factor weights shift conditioned on macro market regime."""
        service = MultiFactorEnsembleService()

        # Bull Regime: Momentum & Smart Money dominate
        w_bull = service.get_regime_weights("BULL_TREND")
        assert w_bull["momentum"] >= 0.40
        assert w_bull["smart_money"] >= 0.25
        assert math.isclose(sum(w_bull.values()), 1.0, abs_tol=1e-3)

        # Bear/Crisis Regime: Low Volatility & Quality dominate
        w_bear = service.get_regime_weights("BEAR_CRISIS")
        assert w_bear["low_vol"] >= 0.40
        assert w_bear["quality"] >= 0.35
        assert math.isclose(sum(w_bear.values()), 1.0, abs_tol=1e-3)

        # Neutral Regime: Quality & Value dominate
        w_neutral = service.get_regime_weights("NEUTRAL_SIDEWAYS")
        assert w_neutral["quality"] >= 0.35
        assert w_neutral["value"] >= 0.25
        assert math.isclose(sum(w_neutral.values()), 1.0, abs_tol=1e-3)

    def test_cross_sectional_factor_scoring(self):
        """Test that cross-sectional ranking correctly ranks high vs low attributes."""
        service = MultiFactorEnsembleService()

        # 3 distinct stocks:
        # NVDA: high momentum, high vol, high P/E
        # JNJ: low vol, high quality, low momentum
        # INTC: low quality, low momentum, cheap value
        candidates = [
            RawFactorMetrics(
                ticker="NVDA",
                momentum_12_1=0.85,
                relative_strength_60d=0.25,
                rsi_14=65.0,
                roe=0.45,
                gross_margin=0.75,
                debt_to_equity=0.40,
                peg_ratio=1.60,
                forward_pe=35.0,
                annualized_vol_60d=0.45,  # High vol
                downside_dev_60d=0.30,
                avwap_distance_pct=0.08,  # Well above AVWAP
                poc_support_pct=0.06,
            ),
            RawFactorMetrics(
                ticker="JNJ",
                momentum_12_1=0.08,
                relative_strength_60d=-0.05,
                rsi_14=52.0,
                roe=0.30,
                gross_margin=0.68,
                debt_to_equity=0.50,
                peg_ratio=2.20,
                forward_pe=16.0,
                annualized_vol_60d=0.12,  # Very low vol
                downside_dev_60d=0.08,
                avwap_distance_pct=0.01,
                poc_support_pct=0.02,
            ),
            RawFactorMetrics(
                ticker="INTC",
                momentum_12_1=-0.20,
                relative_strength_60d=-0.25,
                rsi_14=35.0,
                roe=0.05,
                gross_margin=0.35,
                debt_to_equity=1.20,
                peg_ratio=0.80,   # Deep value
                forward_pe=12.0,  # Deep value
                annualized_vol_60d=0.35,
                downside_dev_60d=0.25,
                avwap_distance_pct=-0.08,
                poc_support_pct=-0.05,
            ),
        ]

        scores = service.score_factor_pillars(candidates)
        assert len(scores) == 3

        scores_by_ticker = {s.ticker: s for s in scores}
        # NVDA should lead in momentum and smart money
        assert scores_by_ticker["NVDA"].momentum_score > scores_by_ticker["JNJ"].momentum_score
        assert scores_by_ticker["NVDA"].smart_money_score > scores_by_ticker["INTC"].smart_money_score

        # JNJ should lead in low volatility
        assert scores_by_ticker["JNJ"].low_vol_score > scores_by_ticker["NVDA"].low_vol_score

        # INTC should lead in value (low P/E, low PEG)
        assert scores_by_ticker["INTC"].value_score > scores_by_ticker["NVDA"].value_score

    def test_regime_style_rotation_leadership(self):
        """Test that market regime automatically rotates the #1 ranked asset."""
        service = MultiFactorEnsembleService()
        candidates = [
            RawFactorMetrics(
                ticker="GROWTH_LEADER",  # High momentum & smart money, higher vol
                momentum_12_1=0.90,
                relative_strength_60d=0.30,
                rsi_14=62.0,
                roe=0.35,
                gross_margin=0.60,
                debt_to_equity=0.50,
                peg_ratio=1.80,
                forward_pe=30.0,
                annualized_vol_60d=0.40,
                downside_dev_60d=0.25,
                avwap_distance_pct=0.10,
                poc_support_pct=0.08,
            ),
            RawFactorMetrics(
                ticker="DEFENSIVE_ANCHOR",  # Ultra low vol & solid quality, low momentum
                momentum_12_1=0.05,
                relative_strength_60d=-0.02,
                rsi_14=50.0,
                roe=0.32,
                gross_margin=0.55,
                debt_to_equity=0.30,
                peg_ratio=2.00,
                forward_pe=18.0,
                annualized_vol_60d=0.10,
                downside_dev_60d=0.06,
                avwap_distance_pct=0.01,
                poc_support_pct=0.02,
            ),
        ]

        # In Bull Market: GROWTH_LEADER should rank #1
        bull_alphas = service.compute_ensemble_alphas(candidates, current_regime="BULL_TREND")
        assert bull_alphas[0].ticker == "GROWTH_LEADER"
        assert bull_alphas[0].rank == 1
        assert "BULL_TREND" in bull_alphas[0].reason

        # In Bear Crisis: DEFENSIVE_ANCHOR should rotate to #1
        bear_alphas = service.compute_ensemble_alphas(candidates, current_regime="BEAR_CRISIS")
        assert bear_alphas[0].ticker == "DEFENSIVE_ANCHOR"
        assert bear_alphas[0].rank == 1
        assert "BEAR_CRISIS" in bear_alphas[0].reason

    def test_composite_score_bounds_and_contributions(self):
        """Test composite alpha score is strictly bounded [0.10, 1.00] and contributions match."""
        service = MultiFactorEnsembleService()
        candidates = [
            RawFactorMetrics(ticker="AAA", momentum_12_1=0.50, roe=0.20, annualized_vol_60d=0.20),
            RawFactorMetrics(ticker="BBB", momentum_12_1=0.10, roe=0.10, annualized_vol_60d=0.30),
        ]
        alphas = service.compute_ensemble_alphas(candidates, current_regime="NEUTRAL_SIDEWAYS")
        for res in alphas:
            assert 0.10 <= res.composite_alpha_score <= 1.00
            sum_contrib = sum(res.factor_contributions.values())
            assert math.isclose(res.composite_alpha_score, max(0.10, min(1.00, sum_contrib)), abs_tol=1e-3)
            assert res.to_dict()["ticker"] == res.ticker

    def test_empty_and_single_candidate_edge_cases(self):
        """Test edge cases with zero or one candidate."""
        service = MultiFactorEnsembleService()
        assert service.compute_ensemble_alphas([]) == []

        single = [RawFactorMetrics(ticker="ONLY_ONE")]
        res = service.compute_ensemble_alphas(single)
        assert len(res) == 1
        assert res[0].ticker == "ONLY_ONE"
        assert res[0].rank == 1
        assert 0.10 <= res[0].composite_alpha_score <= 1.00
