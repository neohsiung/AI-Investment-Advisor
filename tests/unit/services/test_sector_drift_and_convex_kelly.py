"""
Unit Tests for Sector Drift Guard and Asymmetric Convex Kelly Sizing
===================================================================
Tests dynamic universe sector balance, drift prevention, headroom calculation,
asymmetric convex Kelly position sizing, and automated trading integration.
"""
from __future__ import annotations

import math
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.services.kelly_sizing_service import KellyAssessment, KellySizingService
from src.services.quality_gate_service import QualityAssessment
from src.services.sector_drift_guard_service import (
    SECTOR_THEME_LEADERS,
    SectorDistribution,
    SectorDriftGuardService,
    SectorDriftReport,
    SectorDriftStatus,
)
from src.services.universe_lifecycle_service import MacroRegime, UniverseLifecycleService


class DummySettingsService:
    def __init__(self, settings: Optional[Dict[str, Any]] = None):
        self.settings = settings or {}

    def get_setting(self, key: str, default: Any = None) -> Any:
        return self.settings.get(key, default)

    def get(self, user_id: str, key: str, default: Any = None) -> Any:
        return self.settings.get(key, default)


class TestSectorDriftGuardService:
    @pytest.fixture
    def guard_svc(self):
        settings = DummySettingsService({
            "enable_sector_drift_guard": True,
            "sector_concentration_cap_pct": 0.30,
            "sector_drift_warning_pct": 0.25,
        })
        repo = MagicMock()
        repo.get.return_value = None
        market = MagicMock()
        market.get_financials.return_value = None
        market.get_ticker_overview.return_value = None
        return SectorDriftGuardService(
            user_id="test_user",
            settings_service=settings,
            repo=repo,
            market=market,
        )

    def test_ticker_sector_mapping(self, guard_svc):
        assert guard_svc.resolve_ticker_sector("NVDA") == "Technology"
        assert guard_svc.resolve_ticker_sector("AAPL") == "Technology"
        assert guard_svc.resolve_ticker_sector("JPM") == "Financials"
        assert guard_svc.resolve_ticker_sector("LLY") == "Healthcare"
        assert guard_svc.resolve_ticker_sector("CAT") == "Industrials"
        assert guard_svc.resolve_ticker_sector("XOM") == "Energy"
        assert guard_svc.resolve_ticker_sector("NEE") == "Utilities & Clean Energy"
        assert guard_svc.resolve_ticker_sector("UNKNOWN_FOO") == "Unknown"

    def test_analyze_universe_sectors_empty(self, guard_svc):
        report = guard_svc.analyze_universe_sectors(current_active=[])
        assert report.status == SectorDriftStatus.BALANCED
        assert report.distribution.total_items == 0
        assert report.distribution.hhi_index == 0.0
        assert len(report.distribution.over_concentrated_sectors) == 0

    def test_analyze_universe_sectors_balanced(self, guard_svc):
        # 4 tickers across 4 distinct sectors: 25% each
        tickers = [
            {"ticker": "NVDA", "sector": "Technology", "status": "active"},
            {"ticker": "JPM", "sector": "Financials", "status": "active"},
            {"ticker": "LLY", "sector": "Healthcare", "status": "active"},
            {"ticker": "WMT", "sector": "Consumer Staples", "status": "active"},
        ]
        report = guard_svc.analyze_universe_sectors(current_active=tickers)
        assert report.status == SectorDriftStatus.BALANCED
        assert report.distribution.total_items == 4
        # HHI: 4 * (0.25^2) = 0.25
        assert math.isclose(report.distribution.hhi_index, 0.25, abs_tol=1e-3)
        assert report.distribution.over_concentrated_sectors == []

    def test_analyze_universe_sectors_breach(self, guard_svc):
        # 4 Tech, 1 Healthcare -> Tech is 4/5 = 80% > 30% cap
        tickers = [
            {"ticker": "NVDA", "sector": "Technology", "status": "active"},
            {"ticker": "AAPL", "sector": "Technology", "status": "active"},
            {"ticker": "MSFT", "sector": "Technology", "status": "active"},
            {"ticker": "GOOGL", "sector": "Technology", "status": "active"},
            {"ticker": "LLY", "sector": "Healthcare", "status": "active"},
        ]
        report = guard_svc.analyze_universe_sectors(current_active=tickers)
        assert report.status == SectorDriftStatus.DRIFT_BREACH
        assert "Technology" in report.distribution.over_concentrated_sectors
        assert report.distribution.sector_weights["Technology"] == 0.8
        assert len(report.recommendations) > 0

    def test_can_admit_or_rotate_allows_under_cap(self, guard_svc):
        current_active = [
            {"ticker": "JPM", "sector": "Financials"},
            {"ticker": "LLY", "sector": "Healthcare"},
            {"ticker": "WMT", "sector": "Consumer Staples"},
        ]
        allowed, reason = guard_svc.can_admit_or_rotate(
            ticker="NVDA",
            current_active_items=current_active,
            max_active_capacity=10,
        )
        assert allowed is True
        assert "符合" in reason

    def test_can_admit_or_rotate_blocks_over_cap(self, guard_svc):
        # 3 Tech out of 8 total capacity (37.5% > 30% cap)
        current_active = [
            {"ticker": "AAPL", "sector": "Technology"},
            {"ticker": "MSFT", "sector": "Technology"},
            {"ticker": "GOOGL", "sector": "Technology"},
        ]
        allowed, reason = guard_svc.can_admit_or_rotate(
            ticker="NVDA",  # Technology
            current_active_items=current_active,
            max_active_capacity=8,
        )
        assert allowed is False
        assert "集中度上限" in reason
        assert "Technology" in reason

    def test_can_admit_or_rotate_same_sector_rotation(self, guard_svc):
        # Replacing Tech with Tech keeps Tech count same
        current_active = [
            {"ticker": "AAPL", "sector": "Technology"},
            {"ticker": "MSFT", "sector": "Technology"},
        ]
        allowed, reason = guard_svc.can_admit_or_rotate(
            ticker="NVDA",             # Technology
            displaced_ticker="AAPL",    # Technology removed
            current_active_items=current_active,
            max_active_capacity=8,
        )
        assert allowed is True
        assert "符合" in reason

    def test_can_admit_or_rotate_disabled(self):
        settings = DummySettingsService({"enable_sector_drift_guard": False})
        guard = SectorDriftGuardService(user_id="test_user", settings_service=settings)
        allowed, reason = guard.can_admit_or_rotate(
            ticker="NVDA",
            current_active_items=[{"ticker": "AAPL", "sector": "Technology"}],
        )
        assert allowed is True
        assert "disabled" in reason.lower()

    def test_get_sector_headroom(self, guard_svc):
        # Portfolio: $100,000, 30% cap = $30,000
        # Current Tech positions: $10,000 -> Headroom = $20,000 (20%)
        current_positions = [
            {"symbol": "AAPL", "market_value": 6000.0},
            {"symbol": "MSFT", "market_value": 4000.0},
            {"symbol": "JPM", "market_value": 15000.0},
        ]
        headroom_dollars, headroom_pct, sec = guard_svc.get_sector_headroom(
            ticker="NVDA",
            current_positions=current_positions,
            total_nlv=100000.0,
        )
        assert sec == "Technology"
        assert math.isclose(headroom_dollars, 20000.0, abs_tol=1e-2)
        assert math.isclose(headroom_pct, 0.20, abs_tol=1e-3)

    def test_get_sector_headroom_breached(self, guard_svc):
        # Current Tech positions: $35,000 > $30,000 cap -> Headroom = $0.0
        current_positions = [
            {"symbol": "AAPL", "market_value": 20000.0},
            {"symbol": "MSFT", "market_value": 15000.0},
        ]
        headroom_dollars, headroom_pct, sec = guard_svc.get_sector_headroom(
            ticker="NVDA",
            current_positions=current_positions,
            total_nlv=100000.0,
        )
        assert headroom_dollars == 0.0
        assert headroom_pct == 0.0

    def test_discover_theme_and_hot_sector_contenders(self, guard_svc):
        current_active = [
            {"ticker": "NVDA", "sector": "Technology"},
            {"ticker": "JPM", "sector": "Financials"},
        ]
        candidate_pool = ["AAPL", "MSFT"]

        contenders = guard_svc.discover_theme_and_hot_sector_contenders(
            current_active=current_active,
            candidate_pool=candidate_pool,
            max_contenders=5,
        )
        assert len(contenders) <= 5
        # Must not contain active or candidate tickers
        for sym in contenders:
            assert sym not in ["NVDA", "JPM", "AAPL", "MSFT"]


class TestAsymmetricConvexKelly:
    @pytest.fixture
    def kelly_svc(self):
        settings = DummySettingsService({
            "enable_convex_conviction_sizing": True,
            "convex_sizing_gamma": 1.8,
            "kelly_fraction_multiplier": 0.25,
            "kelly_min_position_pct": 0.02,
            "kelly_max_position_pct": 0.20,
        })
        return KellySizingService(
            user_id="test_user",
            settings_service=settings,
        )

    def test_regime_multipliers(self, kelly_svc):
        assert kelly_svc.calculate_regime_multiplier(regime="BULL_GROWTH") == 1.35
        assert kelly_svc.calculate_regime_multiplier(regime="HIGH_VOLATILITY") == 0.50
        assert kelly_svc.calculate_regime_multiplier(regime="INVERSION_DEFENSIVE") == 0.60
        assert kelly_svc.calculate_regime_multiplier(regime="NEUTRAL_BALANCED") == 1.00
        assert kelly_svc.calculate_regime_multiplier(regime=None) == 1.00

    def test_asymmetric_convex_sizing_high_confidence(self, kelly_svc):
        base_size = 0.10
        # High confidence = 9.0 (neutral = 7.0), gamma = 1.8
        sized = kelly_svc.calculate_asymmetric_convex_size(
            base_fractional_size=base_size,
            confidence_score=9.0,
            regime="BULL_GROWTH",
            factor_composite_score=0.85,
        )
        assert sized > base_size
        assert sized <= 0.20  # capped at max_position_pct

    def test_asymmetric_convex_sizing_low_confidence(self, kelly_svc):
        base_size = 0.10
        # Low confidence = 4.0 -> concave damping
        sized = kelly_svc.calculate_asymmetric_convex_size(
            base_fractional_size=base_size,
            confidence_score=4.0,
            regime="NEUTRAL_BALANCED",
        )
        assert sized < base_size
        assert sized >= 0.02  # floor at min_position_pct

    def test_asymmetric_convex_disabled(self):
        settings = DummySettingsService({
            "enable_convex_conviction_sizing": False,
            "kelly_min_position_pct": 0.02,
            "kelly_max_position_pct": 0.20,
        })
        kelly_svc = KellySizingService(user_id="test_user", settings_service=settings)
        base_size = 0.10
        sized = kelly_svc.calculate_asymmetric_convex_size(
            base_fractional_size=base_size,
            confidence_score=8.5,
        )
        # Linear scaling: 8.5 / 8.0 ≈ 1.0625 -> size ≈ 0.10625
        assert sized > base_size

    def test_adjust_size_for_sector_headroom(self, kelly_svc):
        # Portfolio $100,000, 30% cap = $30,000.
        # Current Tech holdings: $25,000 -> Headroom = $5,000 (5%)
        current_positions = [
            {"symbol": "AAPL", "market_value": 15000.0},
            {"symbol": "MSFT", "market_value": 10000.0},
        ]
        # Case 1: Proposed 4% <= 5% headroom -> unchanged
        clamped1, reason1 = kelly_svc.adjust_size_for_sector_headroom(
            recommended_pct=0.04,
            ticker="NVDA",
            current_positions=current_positions,
            total_nlv=100000.0,
        )
        assert clamped1 == 0.04
        assert "符合" in reason1

        # Case 2: Proposed 8% > 5% headroom -> clamped down to 5% (0.05)
        clamped2, reason2 = kelly_svc.adjust_size_for_sector_headroom(
            recommended_pct=0.08,
            ticker="NVDA",
            current_positions=current_positions,
            total_nlv=100000.0,
        )
        assert math.isclose(clamped2, 0.05, abs_tol=1e-3)
        assert "行業額度限制" in reason2


class TestUniverseLifecycleSectorIntegration:
    @pytest.fixture
    def lifecycle_deps(self):
        repo = MagicMock()
        market = MagicMock()
        quality_gate = MagicMock()
        settings = DummySettingsService({
            "universe_auto_refresh_enabled": True,
            "universe_min_quality_score": 6.5,
            "universe_eviction_threshold": 4.0,
            "universe_max_active_tickers": 5,
            "universe_max_candidate_tickers": 10,
            "enable_sector_drift_guard": True,
            "sector_concentration_cap_pct": 0.30,
            "sector_drift_warning_pct": 0.25,
            "universe_require_shadow_validation": False,
        })
        return repo, market, quality_gate, settings

    @pytest.mark.asyncio
    async def test_evolve_candidate_pool_injects_sector_contenders(self, lifecycle_deps):
        repo, market, quality_gate, settings = lifecycle_deps
        # Current candidates has only 1 item (< max 10)
        repo.get_all.side_effect = lambda uid, status: (
            [
                {"ticker": "NVDA", "status": "active", "sector": "Technology"},
                {"ticker": "MSFT", "status": "active", "sector": "Technology"},
            ] if status == "active" else (
                [{"ticker": "AAPL", "status": "candidate", "sector": "Technology"}]
                if status == "candidate" else []
            )
        )

        with patch("src.services.universe_lifecycle_service.SettingsService", return_value=settings):
            service = UniverseLifecycleService(
                user_id="test_user",
                repo=repo,
                market=market,
                quality_gate=quality_gate,
            )
            quality_gate.evaluate_ticker = AsyncMock(
                return_value=QualityAssessment(
                    ticker="LLY",
                    passed=True,
                    overall_score=8.5,
                    hard_gates_passed=True,
                    hard_gate_details={},
                    fundamental_score=8.5,
                    technical_score=8.5,
                    liquidity_score=8.5,
                    reasons=["Excellent"],
                    metrics={},
                    evaluated_at="now",
                )
            )

            res = await service.evolve_candidate_pool(max_candidates=10)
            assert res["success"] is True
            assert repo.upsert.call_count >= 1
            assert res["admitted_new_count"] >= 1

    @pytest.mark.asyncio
    async def test_screen_and_admit_candidates_blocks_over_concentrated_sector(self, lifecycle_deps):
        repo, market, quality_gate, settings = lifecycle_deps
        # 3 Tech already active out of 5 slots (60% > 30% cap)
        current_active = [
            {"ticker": "AAPL", "status": "active", "sector": "Technology"},
            {"ticker": "MSFT", "status": "active", "sector": "Technology"},
            {"ticker": "GOOGL", "status": "active", "sector": "Technology"},
        ]
        repo.get_all.side_effect = lambda uid, status: current_active if status == "active" else []

        with patch("src.services.universe_lifecycle_service.SettingsService", return_value=settings):
            service = UniverseLifecycleService(
                user_id="test_user",
                repo=repo,
                market=market,
                quality_gate=quality_gate,
            )
            quality_gate.evaluate_ticker = AsyncMock(
                return_value=QualityAssessment(
                    ticker="NVDA",
                    passed=True,
                    overall_score=9.0,
                    hard_gates_passed=True,
                    hard_gate_details={},
                    fundamental_score=9.0,
                    technical_score=9.0,
                    liquidity_score=9.0,
                    reasons=["Top"],
                    metrics={},
                    evaluated_at="now",
                )
            )

            admitted = await service.screen_and_admit_candidates(
                candidate_pool=["NVDA"],
                max_active=5,
            )
            # Blocked by drift guard because Technology is already over cap
            assert "NVDA" not in admitted

    @pytest.mark.asyncio
    async def test_run_lifecycle_cycle_contains_sector_drift_report(self, lifecycle_deps):
        repo, market, quality_gate, settings = lifecycle_deps
        repo.get_all.return_value = [
            {"ticker": "NVDA", "status": "active", "sector": "Technology"},
            {"ticker": "JPM", "status": "active", "sector": "Financials"},
        ]

        with patch("src.services.universe_lifecycle_service.SettingsService", return_value=settings):
            service = UniverseLifecycleService(
                user_id="test_user",
                repo=repo,
                market=market,
                quality_gate=quality_gate,
            )
            service.detect_macro_regime = AsyncMock(
                return_value=MacroRegime(
                    regime="BULL_GROWTH",
                    vix=15.0,
                    yield_curve_inverted=False,
                    spy_above_200sma=True,
                    quality_score_adjustment=0.0,
                    summary="Bullish",
                )
            )
            service.review_and_evict_active_tickers = AsyncMock(return_value=[])
            service.evolve_candidate_pool = AsyncMock(return_value={"admitted_new_count": 0, "pruned_count": 0})
            service.evolve_active_pool = AsyncMock(return_value={"rotations": [], "rotation_count": 0})
            service.screen_and_admit_candidates = AsyncMock(return_value=[])

            result = await service.run_lifecycle_cycle()
            assert result["success"] is True
            assert "sector_drift_report" in result
            assert result["sector_drift_report"]["status"] in [
                SectorDriftStatus.BALANCED.value,
                SectorDriftStatus.DRIFT_WARNING.value,
                SectorDriftStatus.DRIFT_BREACH.value,
            ]
