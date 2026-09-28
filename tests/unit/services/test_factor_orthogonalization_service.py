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
