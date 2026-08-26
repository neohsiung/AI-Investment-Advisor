import pytest
import json
from unittest.mock import MagicMock, patch, AsyncMock
from src.services.council_service import CouncilService

@pytest.fixture
def council_service():
    with patch('src.services.council_service.AlchemyVectorRepository'), \
         patch('src.services.council_service.LaneManager'), \
         patch('src.services.council_service.AlchemySettingsRepository'), \
         patch('src.data.database.get_db_engine'):
        yield CouncilService(user_id="test_user")

@pytest.mark.asyncio
async def test_call_agent_llm_success(council_service):
    agent_name = "Momentum"
    context = {"ticker": "AAPL"}
    mock_response = "Bullish momentum detected."
    
    with patch('src.infrastructure.llm.llm_config_chain.build_config_chain') as mock_build_chain:
        mock_build_chain.return_value = ["mock_config"]
        with patch('src.infrastructure.llm.resilient_pipeline.ResilientLLMPipeline.execute', new_callable=AsyncMock) as mock_execute:
            mock_execute.return_value = (mock_response, None)
            with patch('src.utils.prompt_utils.load_agent_prompt', return_value="System prompt"):
                
                result = await council_service._call_agent_llm(agent_name, context)
                
                assert result == mock_response
                mock_execute.assert_called_once()

@pytest.mark.asyncio
async def test_start_session_single(council_service):
    topic = "Analysis of TSLA"
    context_data = {"market_data": {}}
    user_id = "test_user"
    
    with patch.object(council_service, '_run_standard_session', new_callable=AsyncMock) as mock_standard:
        mock_standard.return_value = {"session_id": "123", "consensus": "Buy", "transcript": []}
        
        result = await council_service.start_session(topic, context_data, user_id, scope="single")
        
        assert result["session_id"] == "123"
        mock_standard.assert_called_once()

@pytest.mark.asyncio
async def test_run_map_reduce_portfolio(council_service):
    session_id = "123"
    topic = "Portfolio Analysis"
    context_data = {
        "portfolio": [{"symbol": "AAPL", "quantity": 10}, {"symbol": "MSFT", "quantity": 5}],
        "market_data": {}
    }
    user_id = "test_user"
    
    with patch.object(council_service, '_call_agent_llm', new_callable=AsyncMock) as mock_call:
        async def mock_call_func(agent_name, *args, **kwargs):
            if agent_name == "CIO":
                return "Final CIO Consensus"
            return f"{agent_name} opinion"
        mock_call.side_effect = mock_call_func

        async def fake_run_batch(tasks, batch_size=5):
            return [await t() for t in tasks]

        council_service.lane_manager.run_batch = fake_run_batch

        with patch.object(council_service, '_archive_minutes'):
            result = await council_service._run_map_reduce_portfolio(session_id, topic, context_data, user_id)
            
            assert "Final CIO Consensus" in result["consensus"]
            assert "AAPL" in result["transcript"]
            assert "MSFT" in result["transcript"]
            assert mock_call.call_count >= 5

@pytest.mark.asyncio
async def test_run_debate_logic_with_past_wisdom(council_service):
    session_id = "123"
    topic = "Analysis of NVDA"
    context_data = {"market_data": {}}
    user_id = "test_user"
    
    with patch.object(council_service.vector_repo, 'search_similar_minutes') as mock_search:
        mock_search.return_value = [{"topic": "NVDA", "consensus": "Keep buying"}]
        
        with patch.object(council_service, '_call_agent_llm', new_callable=AsyncMock) as mock_call:
            mock_call.return_value = "Agent opinion"
            
            with patch('src.services.user_focus_service.UserFocusService.get_user_focus', new_callable=AsyncMock, return_value="Growth"):
                with patch.object(council_service, '_archive_minutes'):
                    result = await council_service._run_debate_logic(session_id, topic, context_data, user_id)
                    
                    assert result["session_id"] == "123"
                    assert "Agent opinion" in result["consensus"]
                    # 10 agents + 1 CIO draft + 1 Risk challenge + 1 CIO final
                    # synthesis (P3.1 adversarial round, 2026-07-11) = 13 calls.
                    # Verifier is not called here since market_data is empty.
                    assert mock_call.call_count == 13


@pytest.mark.asyncio
async def test_run_debate_logic_passes_user_id_to_recall(council_service):
    """
    2026-07-14: search_similar_minutes[_by_embedding] previously had no
    user_id filter at all — every tenant's council minutes were
    searchable by every other tenant. Recall calls must be scoped.
    """
    with patch.object(council_service.vector_repo, 'search_similar_minutes') as mock_search:
        mock_search.return_value = []
        with patch.object(council_service, '_call_agent_llm', new_callable=AsyncMock) as mock_call:
            mock_call.return_value = "Agent opinion"
            with patch('src.services.user_focus_service.UserFocusService.get_user_focus', new_callable=AsyncMock, return_value="Growth"):
                with patch.object(council_service, '_archive_minutes'):
                    await council_service._run_debate_logic("s1", "NVDA", {"market_data": {}}, "test_user")

    _, kwargs = mock_search.call_args
    assert kwargs.get("user_id") == "test_user"
    assert kwargs.get("limit") == 5


class TestCompactPastWisdom:
    """
    2026-07-14: k=1 -> k=5 recall; multiple minutes are joined, and only
    compressed via a nano-tier call when the naive join would blow the
    ~300-token budget — otherwise the join is returned as-is (no LLM cost).
    """

    @pytest.mark.asyncio
    async def test_short_join_returned_without_llm_call(self, council_service):
        minutes = [{"topic": "AAPL", "consensus": "Buy"}, {"topic": "TSLA", "consensus": "Hold"}]
        with patch('src.infrastructure.llm.resilient_pipeline.ResilientLLMPipeline.execute',
                   new_callable=AsyncMock) as mock_execute:
            result = await council_service._compact_past_wisdom(minutes)

        mock_execute.assert_not_called()
        assert "AAPL" in result and "Buy" in result
        assert "TSLA" in result and "Hold" in result

    @pytest.mark.asyncio
    async def test_long_join_triggers_nano_tier_compaction(self, council_service):
        minutes = [
            {"topic": f"TICKER{i}", "consensus": "A" * 200}
            for i in range(10)
        ]
        with patch('src.infrastructure.llm.llm_config_chain.build_config_chain') as mock_chain:
            mock_chain.return_value = ["cfg"]
            with patch('src.infrastructure.llm.resilient_pipeline.ResilientLLMPipeline.execute',
                       new_callable=AsyncMock) as mock_execute:
                mock_execute.return_value = ("Compact summary of ten decisions.", None)
                result = await council_service._compact_past_wisdom(minutes)

        mock_execute.assert_called_once()
        assert result == "Compact summary of ten decisions."
        # Verify the nano tier was used for cost control
        call_kwargs = mock_chain.call_args[0]
        assert call_kwargs[1] == "nano"

    @pytest.mark.asyncio
    async def test_compaction_failure_falls_back_to_truncated_join(self, council_service):
        minutes = [{"topic": f"T{i}", "consensus": "B" * 200} for i in range(10)]
        with patch('src.infrastructure.llm.llm_config_chain.build_config_chain', side_effect=Exception("no chain")):
            result = await council_service._compact_past_wisdom(minutes)

        assert len(result) <= council_service._PAST_WISDOM_COMPACT_THRESHOLD_CHARS
        assert result.startswith("Previous related decisions:")

    @pytest.mark.asyncio
    async def test_write_cold_backup(self, council_service, tmp_path):
        # Temporarily redirect backup file path to tmp_path by patching os.path.join
        import os
        orig_join = os.path.join
        def mock_join(*args):
            if "workflow_cold_backup.jsonl" in args:
                return str(tmp_path / "workflow_cold_backup.jsonl")
            return orig_join(*args)
        
        with patch('os.path.join', side_effect=mock_join):
            await council_service._write_cold_backup(
                user_id="test_user",
                session_id="s123",
                topic="Test Cold Backup",
                consensus="Consensus Content",
                verifier_note="Factual check verified"
            )
            
            backup_file = tmp_path / "workflow_cold_backup.jsonl"
            assert backup_file.exists()
            content = backup_file.read_text(encoding="utf-8")
            assert "test_user" in content
            assert "Consensus Content" in content
            assert "Factual check verified" in content
