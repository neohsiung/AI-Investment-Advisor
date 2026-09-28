"""
Unit tests for GeneratedCodeRepository and CanaryShadowRunner database integration.
"""
import uuid
import pytest
from unittest.mock import MagicMock, patch

from src.services.canary_shadow_runner import (
    ArtifactStatus,
    CanaryShadowRunner,
    CodeArtifactRecord,
)
from src.repositories.generated_code_repository import GeneratedCodeRepository


class TestCanaryShadowRunnerPersistence:
    def test_in_memory_and_repo_sync(self):
        runner = CanaryShadowRunner()
        mock_repo = MagicMock(spec=GeneratedCodeRepository)
        runner._repo = mock_repo

        user_id = str(uuid.uuid4())
        art = runner.register_artifact(
            user_id=user_id,
            name="VolPivotFactor",
            description="Exploit volatility spikes",
            source_code="def calculate_factor(df): return df['Close']",
            test_code="def test_factor(): pass",
            ast_hash="testhash123",
            status=ArtifactStatus.PROVISIONAL,
            parameters={"target_regime": "VOLATILITY_PIVOT"},
        )

        assert art.id in runner._store
        assert art.shadow_days_remaining == 14
        assert mock_repo.save_artifact.called

        # Step shadow day
        stepped = runner.step_shadow_day(art.id, simulated_daily_pnl_pct=1.5, signal_strength=0.8)
        assert stepped.shadow_days_remaining == 13
        assert len(stepped.shadow_tracking_log) == 1
        assert mock_repo.update_lifecycle.called

        # Operator approve
        runner.approve_artifact(art.id, user_id)
        assert runner.get_artifact(art.id).status == ArtifactStatus.ACTIVE

        # Operator kill switch
        runner.kill_artifact(art.id, user_id)
        assert runner.get_artifact(art.id).status == ArtifactStatus.KILLED

    def test_shadow_degradation_safeguard(self):
        runner = CanaryShadowRunner()
        runner._repo = False  # in-memory only

        user_id = str(uuid.uuid4())
        art = runner.register_artifact(
            user_id=user_id,
            name="FaultyFactor",
            description="Testing catastrophic drop",
            source_code="pass",
            test_code="pass",
            ast_hash="faultyhash",
            status=ArtifactStatus.PROVISIONAL,
        )

        # Single-day drop > 5% triggers degradation
        stepped = runner.step_shadow_day(art.id, simulated_daily_pnl_pct=-5.5, signal_strength=0.1)
        assert stepped.status == ArtifactStatus.REJECTED
