"""
Unit tests for RuleLifecycleService (Loop 1, B-P2.1): citation tracking,
alpha-based scoring, dedup, and expiry.
規則生命週期服務單元測試：引用追蹤、alpha 計分、去重、過期。
"""
from unittest.mock import MagicMock, patch

import pytest

from src.services.rule_lifecycle_service import RuleLifecycleService


@pytest.fixture
def mock_engine():
    engine = MagicMock()
    conn = MagicMock()
    engine.connect.return_value.__enter__.return_value = conn
    engine.begin.return_value.__enter__.return_value = conn
    return engine, conn


class TestCitation:
    @pytest.mark.asyncio
    async def test_no_active_rules_skips_llm_call(self):
        svc = RuleLifecycleService(user_id="u1")
        with patch("src.agents.structured.invoke_structured") as mock_invoke:
            result = await svc.judge_and_cite("Momentum", "dec-1", "context text", [])
        mock_invoke.assert_not_called()
        assert result == []

    @pytest.mark.asyncio
    async def test_applied_ids_filtered_to_valid_rule_ids(self, mock_engine):
        engine, conn = mock_engine
        svc = RuleLifecycleService(user_id="u1")
        active_rules = [{"id": 1, "rule_text": "- rule A"}, {"id": 2, "rule_text": "- rule B"}]

        parsed = MagicMock()
        parsed.applied_rule_ids = [1, 999]  # 999 doesn't exist in active_rules

        from src.infrastructure.llm.resilient_pipeline import ModelCandidate
        fake_candidate = ModelCandidate("model-1", "openrouter", "google/gemini", MagicMock(), max_retries=0)
        with patch("src.infrastructure.llm.llm_config_chain.build_config_chain", return_value=[fake_candidate]), \
             patch("src.agents.structured.invoke_structured", return_value=(parsed, "raw")), \
             patch("src.data.database.get_db_engine", return_value=engine):
            result = await svc.judge_and_cite("Momentum", "dec-1", "context", active_rules)

        assert result == [1]  # 999 filtered out

    @pytest.mark.asyncio
    async def test_citation_writes_row_and_increments_times_cited(self, mock_engine):
        engine, conn = mock_engine
        svc = RuleLifecycleService(user_id="u1")
        active_rules = [{"id": 1, "rule_text": "- rule A"}]
        parsed = MagicMock()
        parsed.applied_rule_ids = [1]

        from src.infrastructure.llm.resilient_pipeline import ModelCandidate
        fake_candidate = ModelCandidate("model-1", "openrouter", "google/gemini", MagicMock(), max_retries=0)
        with patch("src.infrastructure.llm.llm_config_chain.build_config_chain", return_value=[fake_candidate]), \
             patch("src.agents.structured.invoke_structured", return_value=(parsed, "raw")), \
             patch("src.data.database.get_db_engine", return_value=engine):
            await svc.judge_and_cite("Momentum", "dec-1", "context", active_rules)

        calls = [str(c[0][0]) for c in conn.execute.call_args_list]
        assert any("INSERT INTO rule_citations" in c for c in calls)
        assert any("times_cited = times_cited + 1" in c for c in calls)

    @pytest.mark.asyncio
    async def test_llm_failure_returns_empty_no_raise(self):
        svc = RuleLifecycleService(user_id="u1")
        active_rules = [{"id": 1, "rule_text": "- rule A"}]
        with patch("src.infrastructure.llm.llm_config_chain.build_config_chain", side_effect=Exception("no chain")):
            result = await svc.judge_and_cite("Momentum", "dec-1", "context", active_rules)
        assert result == []


class TestScoreBackfill:
    def test_backfill_score_updates_cited_rules_via_ewma(self, mock_engine):
        engine, conn = mock_engine
        conn.execute.return_value.rowcount = 2
        svc = RuleLifecycleService(user_id="u1")

        with patch("src.data.database.get_db_engine", return_value=engine):
            updated = svc.backfill_score("dec-1", alpha_pct=-3.5)

        assert updated == 2
        calls = conn.execute.call_args_list
        # First call backfills rule_citations.alpha_pct, second updates agent_rules.score
        assert "rule_citations" in str(calls[0][0][0])
        update_sql = str(calls[1][0][0])
        assert "agent_rules" in update_sql
        assert "score = (1 - :ewma) * score + :ewma * :alpha" in update_sql
        params = calls[1][0][1]
        assert params["alpha"] == -3.5

    def test_backfill_score_swallows_db_errors(self):
        svc = RuleLifecycleService(user_id="u1")
        with patch("src.data.database.get_db_engine", side_effect=Exception("db down")):
            result = svc.backfill_score("dec-1", -3.5)
        assert result == 0


class TestExpiry:
    def test_expire_stale_rules_targets_under_cited_or_bad_score(self, mock_engine):
        engine, conn = mock_engine
        conn.execute.return_value.rowcount = 3
        svc = RuleLifecycleService(user_id="u1")

        with patch("src.data.database.get_db_engine", return_value=engine):
            retired = svc.expire_stale_rules(user_id="u1")

        assert retired == 3
        query = str(conn.execute.call_args[0][0])
        assert "status = 'retired'" in query
        assert "times_cited < :min_citations" in query
        assert "score < :floor" in query
        params = conn.execute.call_args[0][1]
        assert params["uid"] == "u1"

    def test_expire_stale_rules_swallows_db_errors(self):
        svc = RuleLifecycleService(user_id="u1")
        with patch("src.data.database.get_db_engine", side_effect=Exception("db down")):
            result = svc.expire_stale_rules()
        assert result == 0


class TestDedup:
    @pytest.mark.asyncio
    async def test_no_pairs_returns_zero_without_llm_call(self, mock_engine):
        engine, conn = mock_engine
        conn.execute.return_value.fetchall.return_value = []
        svc = RuleLifecycleService(user_id="u1")

        with patch("src.data.database.get_db_engine", return_value=engine), \
             patch.object(svc, "_judge_pair") as mock_judge:
            retired = await svc.dedupe_agent_rules("Momentum")

        mock_judge.assert_not_called()
        assert retired == 0

    @pytest.mark.asyncio
    async def test_duplicate_pair_retires_lower_cited_rule(self, mock_engine):
        engine, conn = mock_engine
        pair = MagicMock(id_a=1, text_a="- rule A", id_b=2, text_b="- rule A duplicate")
        conn.execute.return_value.fetchall.return_value = [pair]
        svc = RuleLifecycleService(user_id="u1")

        with patch("src.data.database.get_db_engine", return_value=engine), \
             patch.object(svc, "_judge_pair", return_value="duplicate"):
            retired = await svc.dedupe_agent_rules("Momentum")

        assert retired == 1
        retire_calls = [c for c in conn.execute.call_args_list if "status = 'retired'" in str(c[0][0])]
        assert len(retire_calls) == 1

    @pytest.mark.asyncio
    async def test_distinct_pair_not_retired(self, mock_engine):
        engine, conn = mock_engine
        pair = MagicMock(id_a=1, text_a="- rule A", id_b=2, text_b="- unrelated rule")
        conn.execute.return_value.fetchall.return_value = [pair]
        svc = RuleLifecycleService(user_id="u1")

        with patch("src.data.database.get_db_engine", return_value=engine), \
             patch.object(svc, "_judge_pair", return_value="distinct"):
            retired = await svc.dedupe_agent_rules("Momentum")

        assert retired == 0

    @pytest.mark.asyncio
    async def test_judge_pair_defaults_to_distinct_on_failure(self):
        svc = RuleLifecycleService(user_id="u1")
        with patch("src.infrastructure.llm.llm_config_chain.build_config_chain", side_effect=Exception("no chain")):
            verdict = await svc._judge_pair("- rule A", "- rule B")
        assert verdict == "distinct"


class TestEmbeddingBackfill:
    @pytest.mark.asyncio
    async def test_backfill_embeddings_skips_when_none_missing(self, mock_engine):
        engine, conn = mock_engine
        conn.execute.return_value.fetchall.return_value = []
        svc = RuleLifecycleService(user_id="u1")

        with patch("src.data.database.get_db_engine", return_value=engine):
            updated = await svc.backfill_embeddings("Momentum")

        assert updated == 0

    @pytest.mark.asyncio
    async def test_backfill_embeddings_embeds_missing_rows(self, mock_engine):
        engine, conn = mock_engine
        row = MagicMock(id=1, rule_text="- rule A")
        conn.execute.return_value.fetchall.return_value = [row]
        svc = RuleLifecycleService(user_id="u1")

        with patch("src.data.database.get_db_engine", return_value=engine), \
             patch("src.infrastructure.llm.embedding_service.embed_text", return_value=[0.1] * 768):
            updated = await svc.backfill_embeddings("Momentum")

        assert updated == 1


class TestGating:
    @pytest.mark.asyncio
    async def test_gate_candidate_rules_safety_valve(self, mock_engine):
        engine, conn = mock_engine
        from datetime import datetime, timedelta, timezone
        old_time = datetime.now(timezone.utc) - timedelta(days=15)
        
        candidate_row = MagicMock(
            id=10, agent_name="Momentum", rule_text="- old rule",
            source_decision_id="dec-1", created_at=old_time
        )
        # First query gets candidate rows
        conn.execute.return_value.fetchall.return_value = [candidate_row]
        
        svc = RuleLifecycleService(user_id="u1")
        with patch("src.data.database.get_db_engine", return_value=engine), \
             patch.object(svc, "_refresh_file_cache") as mock_refresh:
            stats = await svc.gate_candidate_rules()
            
        assert stats["checked"] == 1
        assert stats["provisional"] == 1
        assert stats["passed"] == 0
        
        # Verify db update occurred
        update_calls = [c for c in conn.execute.call_args_list if "UPDATE agent_rules" in str(c[0][0])]
        assert len(update_calls) == 1
        assert "gate_status = 'provisional'" in str(update_calls[0][0][0])
        mock_refresh.assert_called_once_with("Momentum", "u1")

    @pytest.mark.asyncio
    async def test_gate_one_no_decisions(self, mock_engine):
        engine, conn = mock_engine
        conn.execute.return_value.fetchall.return_value = []
        svc = RuleLifecycleService(user_id="u1")
        
        with patch("src.data.database.get_db_engine", return_value=engine):
            verdict, details = await svc._gate_one("u1", 10, "Momentum", "- rule", None)
            
        assert verdict == "provisional"
        assert details["sample_size"] == 0
        assert "No historical decisions available" in details["reason"]

    @pytest.mark.asyncio
    async def test_gate_one_passed_evaluation(self, mock_engine):
        engine, conn = mock_engine
        decisions = [
            MagicMock(id="d-1", agent_name="Momentum", ticker="AAPL", signal="BUY", alpha_pct=-1.5, lesson="failed"),
            MagicMock(id="d-2", agent_name="Momentum", ticker="GOOG", signal="BUY", alpha_pct=-2.5, lesson="failed"),
            MagicMock(id="d-3", agent_name="Momentum", ticker="MSFT", signal="BUY", alpha_pct=-0.5, lesson="failed"),
        ]
        conn.execute.return_value.fetchall.return_value = decisions
        
        svc = RuleLifecycleService(user_id="u1")
        parsed = MagicMock(matched_decision_ids=["d-1", "d-2", "d-3"])
        
        from src.infrastructure.llm.resilient_pipeline import ModelCandidate
        fake_candidate = ModelCandidate("model-1", "openrouter", "google/gemini", MagicMock(), max_retries=0)
        
        with patch("src.data.database.get_db_engine", return_value=engine), \
             patch("src.infrastructure.llm.llm_config_chain.build_config_chain", return_value=[fake_candidate]), \
             patch("src.agents.structured.invoke_structured", return_value=(parsed, "raw")):
            verdict, details = await svc._gate_one("u1", 10, "Momentum", "- rule", None)
            
        assert verdict == "passed"
        assert details["matched_ids"] == ["d-1", "d-2", "d-3"]
        assert details["mean_alpha"] == -1.5  # sum(-1.5, -2.5, -0.5) / 3 = -1.5

    @pytest.mark.asyncio
    async def test_gate_one_insufficient_matches(self, mock_engine):
        engine, conn = mock_engine
        decisions = [
            MagicMock(id="d-1", agent_name="Momentum", ticker="AAPL", signal="BUY", alpha_pct=-1.5, lesson="failed"),
            MagicMock(id="d-2", agent_name="Momentum", ticker="GOOG", signal="BUY", alpha_pct=-2.5, lesson="failed"),
        ]
        conn.execute.return_value.fetchall.return_value = decisions
        
        svc = RuleLifecycleService(user_id="u1")
        parsed = MagicMock(matched_decision_ids=["d-1", "d-2"])
        
        from src.infrastructure.llm.resilient_pipeline import ModelCandidate
        fake_candidate = ModelCandidate("model-1", "openrouter", "google/gemini", MagicMock(), max_retries=0)
        
        with patch("src.data.database.get_db_engine", return_value=engine), \
             patch("src.infrastructure.llm.llm_config_chain.build_config_chain", return_value=[fake_candidate]), \
             patch("src.agents.structured.invoke_structured", return_value=(parsed, "raw")):
            verdict, details = await svc._gate_one("u1", 10, "Momentum", "- rule", None)
            
        assert verdict == "provisional"
        assert details["matched_ids"] == ["d-1", "d-2"]
        assert "Insufficient matches" in details["reason"]

    @pytest.mark.asyncio
    async def test_gate_one_rejected_evaluation(self, mock_engine):
        engine, conn = mock_engine
        decisions = [
            MagicMock(id="d-1", agent_name="Momentum", ticker="AAPL", signal="BUY", alpha_pct=0.5, lesson="failed"),
            MagicMock(id="d-2", agent_name="Momentum", ticker="GOOG", signal="BUY", alpha_pct=-0.2, lesson="failed"),
            MagicMock(id="d-3", agent_name="Momentum", ticker="MSFT", signal="BUY", alpha_pct=0.3, lesson="failed"),
        ]
        conn.execute.return_value.fetchall.return_value = decisions
        
        svc = RuleLifecycleService(user_id="u1")
        parsed = MagicMock(matched_decision_ids=["d-1", "d-2", "d-3"])
        
        from src.infrastructure.llm.resilient_pipeline import ModelCandidate
        fake_candidate = ModelCandidate("model-1", "openrouter", "google/gemini", MagicMock(), max_retries=0)
        
        with patch("src.data.database.get_db_engine", return_value=engine), \
             patch("src.infrastructure.llm.llm_config_chain.build_config_chain", return_value=[fake_candidate]), \
             patch("src.agents.structured.invoke_structured", return_value=(parsed, "raw")):
            verdict, details = await svc._gate_one("u1", 10, "Momentum", "- rule", None)
            
        assert verdict == "rejected"
        assert details["mean_alpha"] == 0.2  # sum(0.5, -0.2, 0.3)/3 = 0.2 > -0.5

