"""
Unit tests for FactorOrthogonalizationService and Collinearity Gate.
自研因子正交性與共線性閘門單元測試。
"""

import pytest
from src.services.factor_orthogonalization_service import FactorOrthogonalizationService
from src.services.canary_shadow_runner import CanaryShadowRunner, CodeArtifactRecord, ArtifactStatus


@pytest.fixture
def ortho_service():
    return FactorOrthogonalizationService(max_correlation=0.65)


def test_correlated_returns_blocked(ortho_service):
    """Test that two factors with correlation > 0.65 fail the orthogonality gate."""
    # Active factor with steady upward daily returns
    active_factor = CodeArtifactRecord(
        id="fact-active-1",
        user_id="test_user",
        name="Momentum_Alpha_V1",
        description="Active momentum factor",
        source_code="def score(t): return t.close / t.open",
        test_code="",
        ast_hash="hash1",
        status=ArtifactStatus.ACTIVE,
        shadow_tracking_log=[
            {"date": f"2026-09-{i:02d}", "daily_pnl_pct": 1.0 + i * 0.1}
            for i in range(1, 11)
        ],
    )

    # Candidate factor with nearly identical returns (r ~ 0.99)
    candidate_factor = CodeArtifactRecord(
        id="fact-cand-1",
        user_id="test_user",
        name="Momentum_Alpha_V2_Clone",
        description="Clone of momentum factor",
        source_code="def score(t): return (t.close / t.open) * 1.01",
        test_code="",
        ast_hash="hash2",
        status=ArtifactStatus.PROVISIONAL,
        shadow_tracking_log=[
            {"date": f"2026-09-{i:02d}", "daily_pnl_pct": 1.05 + i * 0.1}
            for i in range(1, 11)
        ],
    )

    res = ortho_service.check_orthogonality(candidate_factor, [active_factor])
    assert res["orthogonal"] is False
    assert res["max_correlation"] > 0.9
    assert res["correlated_with"] == "Momentum_Alpha_V1"
    assert "exceeding max threshold 0.65" in res["reason"]


def test_orthogonal_returns_pass(ortho_service):
    """Test that two uncorrelated factors (r < 0.65) pass the orthogonality gate."""
    active_factor = CodeArtifactRecord(
        id="fact-active-1",
        user_id="test_user",
        name="Momentum_Alpha_V1",
        description="Active momentum factor",
        source_code="def score(t): return t.close",
        test_code="",
        ast_hash="hash1",
        status=ArtifactStatus.ACTIVE,
        shadow_tracking_log=[
            {"date": "2026-09-01", "daily_pnl_pct": 1.0},
            {"date": "2026-09-02", "daily_pnl_pct": -1.0},
            {"date": "2026-09-03", "daily_pnl_pct": 1.0},
            {"date": "2026-09-04", "daily_pnl_pct": -1.0},
            {"date": "2026-09-05", "daily_pnl_pct": 1.0},
            {"date": "2026-09-06", "daily_pnl_pct": -1.0},
        ],
    )

    # Candidate factor: genuinely orthogonal returns (r = 0.0)
    candidate_factor = CodeArtifactRecord(
        id="fact-cand-2",
        user_id="test_user",
        name="Mean_Reversion_V1",
        description="Mean reversion factor",
        source_code="def score(t): return t.low - t.high",
        test_code="",
        ast_hash="hash3",
        status=ArtifactStatus.PROVISIONAL,
        shadow_tracking_log=[
            {"date": "2026-09-01", "daily_pnl_pct": 1.0},
            {"date": "2026-09-02", "daily_pnl_pct": 1.0},
            {"date": "2026-09-03", "daily_pnl_pct": -1.0},
            {"date": "2026-09-04", "daily_pnl_pct": -1.0},
            {"date": "2026-09-05", "daily_pnl_pct": 1.0},
            {"date": "2026-09-06", "daily_pnl_pct": 1.0},
        ],
    )

    res = ortho_service.check_orthogonality(candidate_factor, [active_factor])
    assert res["orthogonal"] is True
    assert res["max_correlation"] < 0.65
    assert "Passed" in res["reason"]


def test_no_active_factors_always_pass(ortho_service):
    """When no active factors exist, candidate passes unconditionally."""
    candidate = CodeArtifactRecord(
        id="fact-1",
        user_id="test_user",
        name="First_Factor",
        description="",
        source_code="",
        test_code="",
        ast_hash="h1",
        status=ArtifactStatus.PROVISIONAL,
    )
    res = ortho_service.check_orthogonality(candidate, [])
    assert res["orthogonal"] is True
    assert res["max_correlation"] == 0.0


def test_code_token_similarity_fallback(ortho_service):
    """When returns series are absent or insufficient, fallback to code token similarity."""
    code = "def calculate_factor(data): return data['close'].rolling(20).mean() / data['close']"
    active_factor = CodeArtifactRecord(
        id="fact-active-code",
        user_id="test_user",
        name="SMA_Factor",
        description="",
        source_code=code,
        test_code="",
        ast_hash="h1",
        status=ArtifactStatus.ACTIVE,
    )
    candidate_factor = CodeArtifactRecord(
        id="fact-cand-code",
        user_id="test_user",
        name="SMA_Factor_Duplicate",
        description="",
        source_code=code,  # Exactly same code
        test_code="",
        ast_hash="h2",
        status=ArtifactStatus.PROVISIONAL,
    )

    res = ortho_service.check_orthogonality(candidate_factor, [active_factor])
    assert res["orthogonal"] is False
    assert res["max_correlation"] >= 0.99
    assert res["correlated_with"] == "SMA_Factor"


def test_canary_runner_evaluation_blocks_collinear_candidate():
    """Test that CanaryShadowRunner.evaluate_auto_promotion blocks promotion if collinear with active factor."""
    runner = CanaryShadowRunner()
    user_id = "test_user"

    # Register an active factor
    active = CodeArtifactRecord(
        id="act-1",
        user_id=user_id,
        name="Active_Trend",
        description="",
        source_code="trend code",
        test_code="",
        ast_hash="a1",
        status=ArtifactStatus.ACTIVE,
        shadow_tracking_log=[
            {"date": f"2026-09-{i:02d}", "daily_pnl_pct": 1.0 + i * 0.2}
            for i in range(1, 15)
        ],
    )
    runner._store["act-1"] = active

    # Candidate meets 14-day graduation & Sharpe gates, but has r > 0.95 with Active_Trend
    candidate = CodeArtifactRecord(
        id="cand-1",
        user_id=user_id,
        name="Candidate_Trend_Clone",
        description="",
        source_code="trend code clone",
        test_code="",
        ast_hash="c1",
        status=ArtifactStatus.PROVISIONAL,
        shadow_days_remaining=0,  # Graduated 14 days
        backtest_metrics={"sharpe_ratio": 2.1, "max_drawdown_pct": 12.0},
        shadow_tracking_log=[
            {"date": f"2026-09-{i:02d}", "daily_pnl_pct": 1.05 + i * 0.2}
            for i in range(1, 15)
        ],
    )
    runner._store["cand-1"] = candidate

    eval_res = runner.evaluate_auto_promotion(candidate)
    assert eval_res["eligible"] is False
    assert "Factor collinearity check failed" in eval_res["reason"]
    assert "Active_Trend" in eval_res["reason"]


def test_canary_runner_evaluation_allows_orthogonal_candidate():
    """Test that CanaryShadowRunner.evaluate_auto_promotion allows promotion if orthogonal."""
    runner = CanaryShadowRunner()
    user_id = "test_user"

    active = CodeArtifactRecord(
        id="act-1",
        user_id=user_id,
        name="Active_Trend",
        description="",
        source_code="trend code",
        test_code="",
        ast_hash="a1",
        status=ArtifactStatus.ACTIVE,
        shadow_tracking_log=[
            {"date": "2026-09-01", "daily_pnl_pct": 1.0},
            {"date": "2026-09-02", "daily_pnl_pct": -1.0},
            {"date": "2026-09-03", "daily_pnl_pct": 1.0},
            {"date": "2026-09-04", "daily_pnl_pct": -1.0},
            {"date": "2026-09-05", "daily_pnl_pct": 1.0},
            {"date": "2026-09-06", "daily_pnl_pct": -1.0},
        ],
    )
    runner._store["act-1"] = active

    candidate = CodeArtifactRecord(
        id="cand-ortho",
        user_id=user_id,
        name="Candidate_StatArb",
        description="",
        source_code="statarb code",
        test_code="",
        ast_hash="c2",
        status=ArtifactStatus.PROVISIONAL,
        shadow_days_remaining=0,
        backtest_metrics={"sharpe_ratio": 1.8, "max_drawdown_pct": 10.0},
        shadow_tracking_log=[
            {"date": "2026-09-01", "daily_pnl_pct": 1.0},
            {"date": "2026-09-02", "daily_pnl_pct": 1.0},
            {"date": "2026-09-03", "daily_pnl_pct": -1.0},
            {"date": "2026-09-04", "daily_pnl_pct": -1.0},
            {"date": "2026-09-05", "daily_pnl_pct": 1.0},
            {"date": "2026-09-06", "daily_pnl_pct": 1.0},
        ],
    )
    runner._store["cand-ortho"] = candidate

    eval_res = runner.evaluate_auto_promotion(candidate)
    assert eval_res["eligible"] is True
    assert eval_res["weight_tier"] == 0.05


# =========================================================================
# Phase 32: Cross-Sectional Orthogonalization & Interaction Unit Tests
# =========================================================================

import numpy as np
from unittest.mock import MagicMock, patch
from src.services.factor_orthogonalization_service import (
    CORE_FACTOR_NAMES,
    CrossSectionalOrthogonalizationResult,
    FactorCollinearityReport,
)
from src.services.tactical_factor_rotation_service import (
    TacticalFactorRotationService,
    TacticalMarketPhase,
)


class TestCrossSectionalFactorOrthogonalization:
    """Tests for Phase 32 Löwdin / Gram-Schmidt orthogonalization, VIF, and interactions."""

    def test_compute_cross_sectional_collinearity_detected(self):
        """驗證當因子間高度共線性時，正確偵測高共線性對與 VIF 警報。"""
        np.random.seed(42)
        n = 20
        # f1 是動能
        f1 = np.random.randn(n)
        # f2 是聰明錢，與動能高度共線 (r ~ 0.95)
        f2 = f1 * 0.95 + np.random.randn(n) * 0.05
        # f3 是低波動，獨立因子
        f3 = np.random.randn(n)

        mat = np.column_stack([f1, f2, f3])
        factor_names = ["momentum", "smart_money", "low_vol"]
        tickers = [f"TICK_{i}" for i in range(n)]

        rep = FactorOrthogonalizationService.compute_cross_sectional_collinearity(
            tickers=tickers,
            matrix=mat,
            factor_names=factor_names,
            max_vif_threshold=5.0,
        )

        assert isinstance(rep, FactorCollinearityReport)
        assert rep.is_collinear_alert is True
        assert rep.max_vif >= 5.0
        assert len(rep.multicollinear_pairs) >= 1
        assert ("momentum", "smart_money") in [(p[0], p[1]) for p in rep.multicollinear_pairs] or (
            ("smart_money", "momentum") in [(p[0], p[1]) for p in rep.multicollinear_pairs]
        )

    def test_lowdin_orthogonalization_eliminates_correlation(self):
        """驗證 Löwdin 對稱正交化將相關矩陣投影為嚴格正交矩陣，VIF 降至接近 1.0。"""
        np.random.seed(123)
        n = 30
        f1 = np.random.randn(n)
        f2 = f1 * 0.85 + np.random.randn(n) * 0.15  # high correlation
        f3 = f1 * -0.70 + np.random.randn(n) * 0.30
        mat = np.column_stack([f1, f2, f3])

        z = FactorOrthogonalizationService.orthogonalize_lowdin(mat)
        assert z.shape == mat.shape

        # 檢驗 Z 的欄位協方差矩陣是否為對角矩陣 (內積為 0)
        cov_z = np.dot(z.T, z) / float(n - 1)
        for i in range(3):
            for j in range(3):
                if i != j:
                    assert pytest.approx(cov_z[i, j], abs=1e-3) == 0.0

    def test_gram_schmidt_orthogonalization_eliminates_correlation(self):
        """驗證 Gram-Schmidt 循序正交化逐次消除投影分量，達成欄向量正交。"""
        np.random.seed(99)
        n = 25
        f1 = np.random.randn(n)
        f2 = f1 * 0.90 + np.random.randn(n) * 0.10
        f3 = np.random.randn(n)
        mat = np.column_stack([f1, f2, f3])

        q = FactorOrthogonalizationService.orthogonalize_gram_schmidt(mat)
        assert q.shape == mat.shape

        cov_q = np.dot(q.T, q) / float(n - 1)
        for i in range(3):
            for j in range(3):
                if i != j:
                    assert pytest.approx(cov_q[i, j], abs=1e-3) == 0.0

    def test_calculate_interaction_terms(self):
        """驗證非線性特徵交互作用項計算並正確映射至 [0.0, 1.0]。"""
        raw_scores = {
            "AAPL": {"momentum": 0.9, "smart_money": 0.8, "quality": 0.9, "value": 0.4, "low_vol": 0.6, "liquidity_premium": 0.8},
            "MSFT": {"momentum": 0.8, "smart_money": 0.7, "quality": 0.95, "value": 0.3, "low_vol": 0.7, "liquidity_premium": 0.75},
            "NVDA": {"momentum": 0.95, "smart_money": 0.9, "quality": 0.8, "value": 0.2, "low_vol": 0.2, "liquidity_premium": 0.95},
            "JNJ": {"momentum": 0.2, "smart_money": 0.3, "quality": 0.85, "value": 0.7, "low_vol": 0.9, "liquidity_premium": 0.4},
        }
        interactions = FactorOrthogonalizationService.calculate_interaction_terms(raw_scores)
        assert "AAPL" in interactions
        assert "mom_x_smart" in interactions["AAPL"]
        assert "qual_x_val" in interactions["AAPL"]
        assert "lowvol_x_qual" in interactions["AAPL"]
        assert "mom_x_liq" in interactions["AAPL"]

        # NVDA has highest mom & smart money -> mom_x_smart should be highest (1.0)
        assert interactions["NVDA"]["mom_x_smart"] == 1.0
        # JNJ has lowest mom & smart money -> mom_x_smart should be 0.0
        assert interactions["JNJ"]["mom_x_smart"] == 0.0

    def test_orthogonalize_cross_section_full_pipeline(self):
        """驗證端到端截面因子正交化流程、相關性消除率與快取。"""
        svc = FactorOrthogonalizationService(user_id="test_user")
        candidate_data = {
            "NVDA": {"momentum_score": 0.95, "smart_money_score": 0.88, "liquidity_premium_score": 0.90, "quality_score": 0.80, "value_score": 0.20, "low_vol_score": 0.15},
            "AMD": {"momentum_score": 0.90, "smart_money_score": 0.85, "liquidity_premium_score": 0.88, "quality_score": 0.75, "value_score": 0.25, "low_vol_score": 0.20},
            "AAPL": {"momentum_score": 0.70, "smart_money_score": 0.75, "liquidity_premium_score": 0.85, "quality_score": 0.92, "value_score": 0.40, "low_vol_score": 0.65},
            "MSFT": {"momentum_score": 0.72, "smart_money_score": 0.80, "liquidity_premium_score": 0.84, "quality_score": 0.95, "value_score": 0.35, "low_vol_score": 0.60},
            "JNJ": {"momentum_score": 0.30, "smart_money_score": 0.35, "liquidity_premium_score": 0.45, "quality_score": 0.88, "value_score": 0.65, "low_vol_score": 0.90},
            "PG": {"momentum_score": 0.35, "smart_money_score": 0.40, "liquidity_premium_score": 0.50, "quality_score": 0.85, "value_score": 0.60, "low_vol_score": 0.88},
        }

        res = svc.orthogonalize_cross_section(candidate_data, method="lowdin")
        assert isinstance(res, CrossSectionalOrthogonalizationResult)
        assert len(res.tickers) == 6
        assert res.method == "lowdin"
        assert res.correlation_reduction_pct >= 50.0

        # 全部分數均應在 [0.0, 1.0] 區間
        for t, scores in res.orthogonal_scores.items():
            for fn, s in scores.items():
                assert 0.0 <= s <= 1.0

        # 快取持久化驗證
        loaded = svc.load_latest_report()
        assert loaded is not None
        assert loaded["method"] == "lowdin"
        assert len(loaded["tickers"]) == 6

    def test_orthogonalize_cross_section_insufficient_tickers_fallback(self):
        """驗證當標的數小於 3 時，正交化安全退化，不拋出異常。"""
        svc = FactorOrthogonalizationService(user_id="test_user")
        candidate_data = {
            "NVDA": {"momentum_score": 0.95, "smart_money_score": 0.88},
            "AAPL": {"momentum_score": 0.70, "smart_money_score": 0.75},
        }
        res = svc.orthogonalize_cross_section(candidate_data)
        assert len(res.tickers) == 2
        assert res.correlation_reduction_pct == 0.0
        assert res.orthogonal_scores["NVDA"]["momentum"] == 0.95


class TestTacticalFactorRotationOrthogonalizationIntegration:
    """Integration tests verifying TacticalFactorRotationService leverages orthogonalized factors."""

    def test_tactical_rotation_applies_orthogonalization(self):
        """驗證 TacticalFactorRotationService.score_candidate_universe 自動啟用正交化與交互作用。"""
        mock_settings = MagicMock()
        configs = {
            "enable_factor_orthogonalization": True,
            "enable_factor_interaction_terms": True,
            "factor_orthogonalization_method": "lowdin",
        }
        mock_settings.get_setting.side_effect = lambda k, default=None, user_id=None: configs.get(k, default)

        svc = TacticalFactorRotationService(user_id="test_user", settings_service=mock_settings)
        universe = {
            "NVDA": {"momentum_score": 0.95, "smart_money_score": 0.88, "liquidity_premium_score": 0.90, "quality_score": 0.80, "value_score": 0.20, "low_vol_score": 0.15, "beta": 1.4},
            "AAPL": {"momentum_score": 0.70, "smart_money_score": 0.75, "liquidity_premium_score": 0.85, "quality_score": 0.92, "value_score": 0.40, "low_vol_score": 0.65, "beta": 1.0},
            "MSFT": {"momentum_score": 0.72, "smart_money_score": 0.80, "liquidity_premium_score": 0.84, "quality_score": 0.95, "value_score": 0.35, "low_vol_score": 0.60, "beta": 1.1},
            "JNJ": {"momentum_score": 0.30, "smart_money_score": 0.35, "liquidity_premium_score": 0.45, "quality_score": 0.88, "value_score": 0.65, "low_vol_score": 0.90, "beta": 0.6},
        }

        scores = svc.score_candidate_universe(universe, phase=TacticalMarketPhase.BULL_ACCELERATION)
        assert len(scores) == 4
        # 應標記正交化為 True
        assert scores[0].factor_breakdown["orthogonalized"] is True
        assert "interactions" in scores[0].factor_breakdown
        assert "正交化: lowdin" in scores[0].reason

    def test_tactical_rotation_disabled_orthogonalization(self):
        """驗證當開關關閉時，使用原始因子分數。"""
        mock_settings = MagicMock()
        mock_settings.get_setting.side_effect = lambda k, default=None, user_id=None: False if k == "enable_factor_orthogonalization" else default

        svc = TacticalFactorRotationService(user_id="test_user", settings_service=mock_settings)
        universe = {
            "NVDA": {"momentum_score": 0.95, "smart_money_score": 0.88, "quality_score": 0.80, "value_score": 0.20, "low_vol_score": 0.15},
            "AAPL": {"momentum_score": 0.70, "smart_money_score": 0.75, "quality_score": 0.92, "value_score": 0.40, "low_vol_score": 0.65},
            "MSFT": {"momentum_score": 0.72, "smart_money_score": 0.80, "quality_score": 0.95, "value_score": 0.35, "low_vol_score": 0.60},
        }

        scores = svc.score_candidate_universe(universe, phase=TacticalMarketPhase.BULL_ACCELERATION)
        assert scores[0].factor_breakdown["orthogonalized"] is False
        assert "interactions" not in scores[0].factor_breakdown


@pytest.mark.asyncio
async def test_conversation_router_ortho_command():
    """驗證 ConversationRouter 對 /ortho 及別名之識別與即時診斷卡片輸出。"""
    from src.services.conversation_router import ConversationRouter

    router = ConversationRouter()
    assert router._is_system_command("/ortho") is True
    assert router._is_system_command("/orthogonal") is True
    assert router._is_system_command("/vif") is True
    assert router._is_system_command("正交化") is True
    assert router._is_system_command("共線性") is True

    resp = await router._handle_system_command(
        adapter=None,
        channel_user_id="user_1",
        text="/ortho",
        resolved_user_id="user_1",
    )
    assert "截面多因子特徵交互作用與動態正交化報告" in resp
    assert "方差膨脹因子 (VIF) 檢定" in resp
    assert "非線性特徵交互作用協同效應" in resp
    assert "Löwdin" in resp

