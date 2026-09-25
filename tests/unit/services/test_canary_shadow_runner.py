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
