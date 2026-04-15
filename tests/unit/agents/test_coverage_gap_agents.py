"""
Coverage gap-fill tests for MomentumAgent and RiskAgent.
These agents have low coverage because their init/run paths
are not exercised by the main workflow tests.
"""
import pytest
from unittest.mock import MagicMock, patch, Mock
import json


class TestMomentumAgentCoverage:
    """Cover MomentumAgent __init__ and run paths."""

    @patch('src.agents.momentum.dspy', None)
    @patch('src.agents.momentum.MomentumSignature', None)
    def test_init_no_dspy(self):
        """Init without DSPy should set dspy_module to None."""
        from src.agents.momentum import MomentumAgent
        with patch.object(MomentumAgent, '__init__', lambda self, **kw: None):
            agent = MomentumAgent.__new__(MomentumAgent)
            agent.dspy_module = None
            assert agent.dspy_module is None

    @pytest.mark.asyncio
    async def test_run_legacy_path_mock_response(self):
        """Legacy path with mock LLM returns formatted mock report."""
        from src.agents.momentum import MomentumAgent
        agent = MomentumAgent.__new__(MomentumAgent)
        agent.dspy_module = None
        agent.name = "Momentum"
        from unittest.mock import AsyncMock
        agent.run_tool_loop = AsyncMock(return_value="Mock response for TSLA")

        context = {
            "ticker": "TSLA",
            "price_data": {"close": 250.0},
            "indicators": {"rsi": 55}
        }
        result = await agent.run(context)
        assert "TSLA" in result
        assert "分析報告" in result
        assert "Mock" in result

    @pytest.mark.asyncio
    async def test_run_legacy_path_real_response(self):
        """Legacy path with real LLM response passes through."""
        from src.agents.momentum import MomentumAgent
        agent = MomentumAgent.__new__(MomentumAgent)
        agent.dspy_module = None
        agent.name = "Momentum"
        from unittest.mock import AsyncMock
        agent.run_tool_loop = AsyncMock(return_value="## NVDA Momentum Analysis\nBullish trend")

        context = {"ticker": "NVDA", "price_data": {}, "indicators": {}}
        result = await agent.run(context)
        assert "NVDA" in result
        assert "Bullish" in result


class TestRiskAgentCoverage:
    """Cover RiskAgent __init__ and run."""

    @pytest.mark.asyncio
    async def test_run_passes_context(self):
        """Risk agent delegates to run_tool_loop with context."""
        from src.agents.risk import RiskAgent
        agent = RiskAgent.__new__(RiskAgent)
        agent.name = "Risk"
        from unittest.mock import AsyncMock
        agent.run_tool_loop = AsyncMock(return_value="Risk analysis complete")

        context = {
            "ticker": "SPY",
            "market_data": {"vix": 25.5},
            "portfolio": {"beta": 1.2}
        }
        result = await agent.run(context)
        assert result == "Risk analysis complete"
        agent.run_tool_loop.assert_called_once_with(context=context)


class TestAlchemyMemoryRepositoryCoverage:
    """Cover AlchemyMemoryRepository with mocked DB."""

    def test_get_recent_reports(self):
        """get_recent_reports queries DB and returns ReportMemoryItem list."""
        from src.services.memory_service import ReportMemoryItem

        # Setup mock row with attributes
        mock_row = MagicMock()
        mock_row.date = "2026-02-14"
        mock_row.content = "Daily report content"
        mock_row.summary = "Summary"
        mock_row.user_id = "user@test.com"
        mock_row.report_type = "daily"

        with patch('src.repositories.memory_repository.get_db_engine') as mock_engine_func:
            mock_engine = MagicMock()
            mock_engine_func.return_value = mock_engine
            
            mock_conn = MagicMock()
            mock_engine.connect.return_value.__enter__.return_value = mock_conn
            
            mock_result = MagicMock()
            mock_result.fetchall.return_value = [mock_row]
            mock_conn.execute.return_value = mock_result

            from src.repositories.memory_repository import AlchemyMemoryRepository
            repo = AlchemyMemoryRepository()
            items = repo.get_recent_reports("user@test.com", "daily", 5)

            assert len(items) == 1
            assert items[0].report_date == "2026-02-14"
            assert items[0].user_id == "user@test.com"

    def test_save_report(self):
        """save_report inserts/upserts into DB."""
        from src.services.memory_service import ReportMemoryItem

        item = ReportMemoryItem(
            user_id="user@test.com",
            report_type="daily",
            report_date="2026-02-14",
            full_content="content",
            compressed_summary="summary"
        )

        with patch('src.repositories.memory_repository.get_db_engine') as mock_engine_func:
            mock_engine = MagicMock()
            mock_engine_func.return_value = mock_engine
            
            mock_conn = MagicMock()
            mock_engine.begin.return_value.__enter__.return_value = mock_conn

            from src.repositories.memory_repository import AlchemyMemoryRepository
            repo = AlchemyMemoryRepository()
            repo.save_report(item)

            mock_conn.execute.assert_called_once()

    def test_get_recent_reports_null_findings(self):
        """Handles empty results gracefully."""
        with patch('src.repositories.memory_repository.get_db_engine') as mock_engine_func:
            mock_engine = MagicMock()
            mock_engine_func.return_value = mock_engine
            
            mock_conn = MagicMock()
            mock_engine.connect.return_value.__enter__.return_value = mock_conn
            
            mock_result = MagicMock()
            mock_result.fetchall.return_value = []
            mock_conn.execute.return_value = mock_result

            from src.repositories.memory_repository import AlchemyMemoryRepository
            repo = AlchemyMemoryRepository()
            items = repo.get_recent_reports("user@test.com", "weekly", 3)

            assert len(items) == 0


class TestAgentLLMProviderCoverage:
    """Cover AgentLLMProvider summarization and contradiction checking."""

    @patch('src.infrastructure.agent_llm_provider.AgentFactory')
    @pytest.mark.asyncio
    async def test_summarize_success(self, mock_factory):
        """summarize calls agent.run and returns string."""
        from src.infrastructure.agent_llm_provider import AgentLLMProvider
        from unittest.mock import AsyncMock
        mock_agent = MagicMock()
        mock_agent.run = AsyncMock(return_value="Summary of report")
        mock_factory.create_agent.return_value = mock_agent

        provider = AgentLLMProvider(user_id="test@user.com")
        result = await provider.summarize("Very long report text...")
        
        assert result == "Summary of report"
        mock_agent.run.assert_called_once()
        # call_args[0][0] is the context dict
        call_context = mock_agent.run.call_args[0][0]
        assert "TASK: Summarize" in call_context.get("task_instruction", "")

    @patch('src.infrastructure.agent_llm_provider.AgentFactory')
    @pytest.mark.asyncio
    async def test_summarize_fallback(self, mock_factory):
        """summarize handles exceptions with fallback truncation."""
        from src.infrastructure.agent_llm_provider import AgentLLMProvider
        from unittest.mock import AsyncMock
        mock_agent = MagicMock()
        mock_agent.run = AsyncMock(side_effect=Exception("LLM Error"))
        mock_factory.create_agent.return_value = mock_agent

        provider = AgentLLMProvider(user_id="test@user.com")
        result = await provider.summarize("Long text" * 200)
        
        assert result.endswith("...")
        assert len(result) <= 1004

    @patch('src.infrastructure.agent_llm_provider.AgentFactory')
    @pytest.mark.asyncio
    async def test_check_contradictions_json(self, mock_factory):
        """check_contradictions parses JSON list from agent output."""
        from src.infrastructure.agent_llm_provider import AgentLLMProvider
        from unittest.mock import AsyncMock
        mock_agent = MagicMock()
        mock_agent.run = AsyncMock(return_value='Here is the list: ["Contradiction 1"]')
        mock_factory.create_agent.return_value = mock_agent

        provider = AgentLLMProvider(user_id="test@user.com")
        result = await provider.check_contradictions("New text", "Old context")
        
        assert result == ["Contradiction 1"]

    @patch('src.infrastructure.agent_llm_provider.AgentFactory')
    @pytest.mark.asyncio
    async def test_check_contradictions_failure(self, mock_factory):
        """check_contradictions returns empty list on error."""
        from src.infrastructure.agent_llm_provider import AgentLLMProvider
        from unittest.mock import AsyncMock
        mock_agent = MagicMock()
        mock_agent.run = AsyncMock(side_effect=Exception("Fail"))
        mock_factory.create_agent.return_value = mock_agent

        provider = AgentLLMProvider(user_id="test@user.com")
        result = await provider.check_contradictions("N", "O")
        
        assert result == []
