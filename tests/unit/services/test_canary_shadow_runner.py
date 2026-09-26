"""
Unit Tests for CanaryShadowRunner
=================================
驗測金絲雀灰度週期管理、14 日步進、模擬損益異常熔斷、手動核准與緊急 Kill-Switch。
"""
import pytest
from src.services.canary_shadow_runner import (
    ArtifactStatus,
    CanaryShadowRunner,
)


@pytest.fixture
def runner() -> CanaryShadowRunner:
    return CanaryShadowRunner()


def test_canary_registration_and_listing(runner: CanaryShadowRunner):
    record = runner.register_artifact(
        user_id="user_123",
        name="alpha_momentum",
        description="Test momentum factor",
        source_code="def calc(): pass",
        test_code="def test(): pass",
        ast_hash="abc123hash",
        status=ArtifactStatus.PROVISIONAL,
    )

    assert record.id is not None
    assert record.status == ArtifactStatus.PROVISIONAL
    assert record.shadow_days_remaining == 14

    items = runner.list_artifacts(user_id="user_123")
    assert len(items) == 1
    assert items[0].name == "alpha_momentum"


def test_canary_step_shadow_day_and_completion(runner: CanaryShadowRunner):
    record = runner.register_artifact(
        user_id="user_123",
        name="alpha_momentum",
        description="Test momentum factor",
        source_code="def calc(): pass",
        test_code="",
        ast_hash="abc",
        status=ArtifactStatus.PROVISIONAL,
    )

    # Step 1 day with positive performance
    updated = runner.step_shadow_day(record.id, simulated_daily_pnl_pct=1.5, signal_strength=0.8)
    assert updated.shadow_days_remaining == 13
    assert len(updated.shadow_tracking_log) == 1
    assert updated.status == ArtifactStatus.PROVISIONAL


def test_canary_safeguard_triggers_on_large_drawdown(runner: CanaryShadowRunner):
    record = runner.register_artifact(
        user_id="user_123",
        name="risky_factor",
        description="Risky factor",
        source_code="",
        test_code="",
        ast_hash="xyz",
        status=ArtifactStatus.PROVISIONAL,
    )

    # Extreme -6% drop triggers safeguard rejection
    updated = runner.step_shadow_day(record.id, simulated_daily_pnl_pct=-6.0, signal_strength=0.1)
    assert updated.status == ArtifactStatus.REJECTED


def test_canary_manual_approval_and_kill(runner: CanaryShadowRunner):
    record = runner.register_artifact(
        user_id="user_123",
        name="factor_to_approve",
        description="Factor",
        source_code="",
        test_code="",
        ast_hash="hash",
        status=ArtifactStatus.PROVISIONAL,
    )

    # Operator approves
    approved = runner.approve_artifact(record.id, user_id="user_123")
    assert approved is True
    assert record.status == ArtifactStatus.ACTIVE

    # Operator triggers kill switch
    killed = runner.kill_artifact(record.id, user_id="user_123")
    assert killed is True
    assert record.status == ArtifactStatus.KILLED


def test_auto_enroll_verified_artifacts(runner: CanaryShadowRunner):
    rec = runner.register_artifact(
        user_id="user_test",
        name="verified_factor",
        description="Factor in verified status",
        source_code="def calc(): pass",
        test_code="",
        ast_hash="h1",
        status=ArtifactStatus.VERIFIED,
    )
    assert rec.status == ArtifactStatus.VERIFIED

    enrolled = runner.auto_enroll_verified_artifacts(user_id="user_test")
    assert len(enrolled) == 1
    assert enrolled[0].id == rec.id
    assert enrolled[0].status == ArtifactStatus.PROVISIONAL
    assert enrolled[0].shadow_days_remaining == 14


def test_evaluate_and_execute_auto_promotion(runner: CanaryShadowRunner):
    rec = runner.register_artifact(
        user_id="user_test",
        name="promotable_factor",
        description="Factor with high metrics",
        source_code="def calc(): pass",
        test_code="",
        ast_hash="h2",
        status=ArtifactStatus.PROVISIONAL,
        backtest_metrics={
            "sharpe_ratio": 1.85,
            "max_drawdown_pct": 12.0,
            "wfe": 0.85,
            "monte_carlo_win_rate": 88.0,
        },
    )

    # 1. Initially 14 days remaining - not eligible yet
    eval_init = runner.evaluate_auto_promotion(rec)
    assert eval_init["eligible"] is False

    # 2. Step 7 positive days
    for _ in range(7):
        runner.step_shadow_day(rec.id, simulated_daily_pnl_pct=0.8, signal_strength=0.9)

    assert rec.shadow_days_remaining == 7
    assert len(rec.shadow_tracking_log) == 7

    # 3. Now meets fast-track criteria (WFE >= 0.70, MC >= 75%, positive cum pnl)
    eval_fast = runner.evaluate_auto_promotion(rec)
    assert eval_fast["eligible"] is True
    assert eval_fast["weight_tier"] == 0.05

    # 4. Auto-promote
    ok = runner.auto_promote_artifact(rec.id, user_id="user_test")
    assert ok is True
    assert rec.status == ArtifactStatus.ACTIVE
    assert rec.parameters["approval_type"] == "automated"
    assert rec.parameters["weight_cap"] == 0.05

    # 5. Check effective weight cap starts at 5%
    weight_cap = runner.get_effective_weight_cap(rec)
    assert weight_cap == 0.05


def test_auto_promotion_rejected_on_drawdown(runner: CanaryShadowRunner):
    rec = runner.register_artifact(
        user_id="user_test",
        name="dropping_factor",
        description="Factor with severe drawdown",
        source_code="",
        test_code="",
        ast_hash="h3",
        status=ArtifactStatus.PROVISIONAL,
        backtest_metrics={"sharpe_ratio": 1.5, "max_drawdown_pct": 10.0},
    )

    # Trigger -5.5% drop
    runner.step_shadow_day(rec.id, simulated_daily_pnl_pct=-5.5, signal_strength=0.2)
    assert rec.status == ArtifactStatus.REJECTED

    # Not eligible
    eval_res = runner.evaluate_auto_promotion(rec)
    assert eval_res["eligible"] is False

