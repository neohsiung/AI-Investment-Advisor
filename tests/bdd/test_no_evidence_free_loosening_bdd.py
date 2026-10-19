"""
BDD scenarios: no loosening without evidence (ADR-003 / M-A0).
行為規格：無證據不放寬（ADR-003 / M-A0）。
"""
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.services.adaptive_council_meta_learning_service import AdaptiveCouncilMetaLearningService
from src.services.rule_lifecycle_service import RuleLifecycleService
from src.services.universe_lifecycle_service import UniverseLifecycleService


class TestNoEvidenceFreeLoosening:
    @pytest.mark.asyncio
    async def test_given_candidate_rule_20_days_old_when_cycle_runs_then_expired_not_promoted(self):
        # Given a candidate rule created 20 days ago
        engine = MagicMock()
        conn = MagicMock()
        engine.connect.return_value.__enter__.return_value = conn
        engine.begin.return_value.__enter__.return_value = conn
        row = MagicMock(id=7, agent_name="Macro", rule_text="- r", source_decision_id=None,
                        created_at=datetime.now(timezone.utc) - timedelta(days=20))
        conn.execute.return_value.fetchall.return_value = [row]
        svc = RuleLifecycleService(user_id="u1")
        # When the lifecycle cycle runs
        with patch("src.data.database.get_db_engine", return_value=engine):
            stats = await svc.gate_candidate_rules()
        # Then it is expired, not promoted
        assert stats["expired"] == 1 and stats["provisional"] == 0 and stats["passed"] == 0
        updates = " ".join(str(c[0][0]) for c in conn.execute.call_args_list if "UPDATE agent_rules" in str(c[0][0]))
        assert "status = 'rejected'" in updates
        assert "status = 'active'" not in updates

    def test_given_zero_settled_rows_when_council_context_built_then_no_weights_injected(self):
        # Given no settled decision outcomes
        svc = AdaptiveCouncilMetaLearningService(user_id="u1")
        conn = MagicMock()
        conn.execute.return_value.fetchall.return_value = []
        svc.engine = MagicMock()
        svc.engine.connect.return_value.__enter__.return_value = conn
        # When the council context is built
        ctx = svc.generate_adaptive_council_context()
        # Then no weights are injected
        assert ctx.meta_weights == {}
        assert "專家動態決策影響力權重" not in ctx.prompt_guidance

    @pytest.mark.asyncio
    async def test_given_qualified_shadow_candidate_then_it_is_not_promoted(self):
        # Given a universe lifecycle with a qualified shadow candidate
        settings = MagicMock()
        settings.get_setting.side_effect = lambda k: {"universe_max_active_tickers": 5}.get(k)
        repo = MagicMock()
        repo.get_all.return_value = []
        with patch("src.services.universe_lifecycle_service.SettingsService", return_value=settings), \
             patch("src.services.shadow_ledger_service.ShadowLedgerService") as shadow_cls:
            shadow = shadow_cls.return_value
            shadow.batch_step_and_evaluate = AsyncMock(
                return_value={"graduated_count": 0, "in_progress_count": 1, "failed_count": 0,
                              "qualified_tickers": ["AAA"]})
            svc = UniverseLifecycleService(user_id="u1", repo=repo, market=MagicMock(), quality_gate=MagicMock())
            with patch.object(svc, "detect_macro_regime", AsyncMock(return_value=MagicMock(quality_score_adjustment=0.0))), \
                 patch.object(svc, "review_and_evict_active_tickers", AsyncMock(return_value=[])), \
                 patch.object(svc, "evolve_candidate_pool", AsyncMock(return_value={})), \
                 patch.object(svc, "evolve_active_pool", AsyncMock(return_value={})), \
                 patch.object(svc, "screen_and_admit_candidates", AsyncMock(return_value=[])):
                try:
                    # When the lifecycle cycle runs
                    await svc.run_lifecycle_cycle(force=True)
                except Exception:
                    pass
        # Then the shadow ledger is evaluated without promotion
        assert shadow.batch_step_and_evaluate.await_args.kwargs["auto_promote"] is False
