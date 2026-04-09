"""
Tests for Phase 2 extracted modules: ContextAssembler, WalProtocol, AgentLoop.
Phase 2 提取模組的測試：ContextAssembler、WalProtocol、AgentLoop。
"""

import pytest
import json
import os
import tempfile
from unittest.mock import MagicMock, patch, mock_open

from src.agents.context import ContextAssembler
from src.agents.wal_protocol import WalProtocol
from src.agents.agent_loop import AgentLoop


# ──────────────────────────────────────────────────────
# ContextAssembler Tests
# ──────────────────────────────────────────────────────

class TestContextAssembler:

    @pytest.fixture
    def assembler(self):
        skill_loader = MagicMock()
        skill_loader.get_skill_registry_xml.return_value = "<skills>test</skills>"
        memory = MagicMock()
        memory.search.return_value = []
        toold = MagicMock()
        toold.list_tools.return_value = [{"name": "get_price", "params": {}}]
        return ContextAssembler(
            skill_loader=skill_loader, memory=memory, toold=toold
        )

    def test_render_basic_template(self, assembler):
        """Test basic Jinja2 rendering with time injection."""
        prompt = "Time: {{ current_time }} | Data: {{ data }}"
        result = assembler.render(prompt, {"data": "test"})
        assert "Time:" in result
        assert "test" in result

    def test_render_injects_tools(self, assembler):
        """Test that MCP tools JSON is injected."""
        prompt = "Tools: {{ tools }}"
        result = assembler.render(prompt, {})
        assert "get_price" in result

    def test_render_injects_skills_xml(self, assembler):
        """Test that skills XML is injected."""
        prompt = "Skills: {{ skills_xml }}"
        result = assembler.render(prompt, {})
        assert "<skills>test</skills>" in result

    def test_render_injects_historical_context(self, assembler):
        """Test explicit historical context injection."""
        prompt = "Memory: {{ memory_context }}"
        result = assembler.render(prompt, {"historical_context": "Previous analysis..."})
        assert "Previous analysis..." in result

    def test_render_injects_topic_memory(self):
        """Test topic-based memory search injection."""
        memory = MagicMock()
        memory.search.return_value = [
            {"content": "AAPL rose 5%", "score": 0.95}
        ]
        assembler = ContextAssembler(memory=memory)
        prompt = "Memory: {{ memory_context }}"
        result = assembler.render(prompt, {"topic": "AAPL"})
        assert "AAPL rose 5%" in result
        memory.search.assert_called_once_with("AAPL", query_vector=None, limit=3)

    def test_render_no_double_memory_injection(self):
        """If historical_context exists, topic search should be skipped."""
        memory = MagicMock()
        assembler = ContextAssembler(memory=memory)
        prompt = "{{ memory_context }}"
        assembler.render(prompt, {"historical_context": "X", "topic": "AAPL"})
        memory.search.assert_not_called()

    def test_render_fallback_on_error(self, assembler):
        """On rendering error, return raw system prompt."""
        assembler._toold.list_tools.side_effect = Exception("broken")
        result = assembler.render("Hello {{ undefined_var }}", {})
        # Should return the raw prompt on error
        assert "Hello" in result

    def test_render_user_context_dict(self):
        """Test static method for dict context."""
        result = ContextAssembler.render_user_context({"a": 1})
        assert '"a": 1' in result

    def test_render_user_context_str(self):
        """Test static method for string context."""
        assert ContextAssembler.render_user_context("hello") == "hello"

    def test_render_with_none_dependencies(self):
        """Test rendering when all dependencies are None."""
        assembler = ContextAssembler()
        result = assembler.render("Hello {{ current_time }}", {})
        assert "Hello" in result


# ──────────────────────────────────────────────────────
# WalProtocol Tests
# ──────────────────────────────────────────────────────

class TestWalProtocol:

    def test_estimate_tokens(self):
        """4 chars ≈ 1 token."""
        assert WalProtocol.estimate_tokens("abcd") == 1
        assert WalProtocol.estimate_tokens("a" * 100) == 25

    def test_check_context_window_below_limit(self):
        """Messages below limit should return False."""
        wal = WalProtocol()
        messages = [{"content": "a" * 100}]  # 25 tokens
        assert wal.check_context_window(messages, max_tokens=32000) is False

    def test_check_context_window_above_limit(self):
        """Messages above limit should return True."""
        wal = WalProtocol()
        # 120000 chars = 30000 tokens, with reserve_floor=4000, limit=32000
        messages = [{"content": "a" * 120000}]
        assert wal.check_context_window(messages, reserve_floor=4000, max_tokens=32000) is True

    def test_perform_silent_flush_writes_state_file(self):
        """Verify STATE.md is written during flush."""
        with tempfile.TemporaryDirectory() as tmpdir:
            wal = WalProtocol(workspace_path=tmpdir, agent_name="TestAgent")
            mock_llm = MagicMock(return_value="WAL_CHECKPOINT: summary")

            messages = [
                {"role": "system", "content": "sys"},
                {"role": "user", "content": "q1"},
                {"role": "assistant", "content": "a1"},
                {"role": "user", "content": "q2"},
            ]

            wal.perform_silent_flush(messages, mock_llm)

            # Verify STATE.md was written
            state_path = os.path.join(tmpdir, "STATE.md")
            assert os.path.exists(state_path)
            content = open(state_path).read()
            assert "WAL_CHECKPOINT" in content

    def test_perform_silent_flush_truncates_history(self):
        """Verify messages are truncated to [system, checkpoint]."""
        wal = WalProtocol(agent_name="TestAgent")
        mock_llm = MagicMock(return_value="Summary")

        messages = [
            {"role": "system", "content": "sys"},
            {"role": "user", "content": "q1"},
            {"role": "assistant", "content": "a1"},
            {"role": "user", "content": "q2"},
        ]

        wal.perform_silent_flush(messages, mock_llm)

        assert len(messages) == 2
        assert messages[0]["role"] == "system"
        assert "Session Restored" in messages[1]["content"]

    def test_perform_silent_flush_with_redaction(self):
        """Verify redact_fn is called on WAL state before file write."""
        with tempfile.TemporaryDirectory() as tmpdir:
            redact_fn = MagicMock(side_effect=lambda x: x.replace("secret", "[REDACTED]"))
            wal = WalProtocol(workspace_path=tmpdir, agent_name="Test", redact_fn=redact_fn)
            mock_llm = MagicMock(return_value="WAL: secret data")

            messages = [
                {"role": "system", "content": "sys"},
                {"role": "user", "content": "q1"},
                {"role": "assistant", "content": "a1"},
                {"role": "user", "content": "q2"},
            ]

            wal.perform_silent_flush(messages, mock_llm)

            state_content = open(os.path.join(tmpdir, "STATE.md")).read()
            assert "[REDACTED]" in state_content
            redact_fn.assert_called_once()

    def test_perform_silent_flush_handles_llm_error(self):
        """LLM error should not raise, just log."""
        wal = WalProtocol(agent_name="TestAgent")
        mock_llm = MagicMock(side_effect=Exception("LLM Down"))

        messages = [
            {"role": "system", "content": "sys"},
            {"role": "user", "content": "q1"},
            {"role": "assistant", "content": "a1"},
            {"role": "user", "content": "q2"},
        ]
        original_len = len(messages)

        # Should not raise
        wal.perform_silent_flush(messages, mock_llm)
        # Messages unchanged since error happened before truncation
        assert len(messages) == original_len

    def test_no_truncation_if_short_history(self):
        """Messages with <= 3 entries should not be truncated."""
        wal = WalProtocol(agent_name="TestAgent")
        mock_llm = MagicMock(return_value="Summary")

        messages = [
            {"role": "system", "content": "sys"},
            {"role": "user", "content": "q1"},
        ]

        wal.perform_silent_flush(messages, mock_llm)
        assert len(messages) == 2  # Unchanged


# ──────────────────────────────────────────────────────
# AgentLoop Tests
# ──────────────────────────────────────────────────────

class TestAgentLoop:

    @pytest.mark.asyncio
    async def test_execute_no_tool_call(self):
        """Direct LLM response without tool call should return immediately."""
        loop = AgentLoop(agent_name="Test")
        mock_llm = MagicMock(return_value="Final answer: 42")

        messages = [
            {"role": "system", "content": "sys"},
            {"role": "user", "content": "What is 42?"},
        ]

        result = await loop.execute(messages, call_llm_fn=mock_llm)
        assert result == "Final answer: 42"
        mock_llm.assert_called_once()

    @pytest.mark.asyncio
    async def test_execute_with_search_tool(self):
        """Test SEARCH tool parsing and execution."""
        search_svc = MagicMock()
        from unittest.mock import AsyncMock
        search_svc.search_financial_context = AsyncMock(return_value=[
            {"title": "AAPL", "snippet": "Stock up 5%", "link": "url1"}
        ])
        loop = AgentLoop(agent_name="Test", search_service=search_svc)
        mock_llm = MagicMock(side_effect=[
            'SEARCH: "AAPL stock"',
            "Final: AAPL is up.",
        ])

        messages = [
            {"role": "system", "content": "sys"},
            {"role": "user", "content": "Check AAPL"},
        ]

        result = await loop.execute(messages, call_llm_fn=mock_llm)
        assert result == "Final: AAPL is up."
        search_svc.search_financial_context.assert_called_once_with("AAPL stock")

    @pytest.mark.asyncio
    async def test_execute_with_mcp_tool(self):
        """Test MCP tool call execution."""
        toold = MagicMock()
        toold.tools = {"get_price": True}
        from unittest.mock import AsyncMock
        toold.call_tool = AsyncMock(return_value={"price": 150})
        loop = AgentLoop(agent_name="Test", toold=toold)
        mock_llm = MagicMock(side_effect=[
            'CALL: get_price({"ticker": "AAPL"})',
            "AAPL is $150",
        ])

        messages = [
            {"role": "system", "content": "sys"},
            {"role": "user", "content": "AAPL price?"},
        ]

        result = await loop.execute(messages, call_llm_fn=mock_llm)
        assert result == "AAPL is $150"
        toold.call_tool.assert_called_once_with("get_price", {"ticker": "AAPL"})

    @pytest.mark.asyncio
    async def test_execute_respects_max_turns(self):
        """After max turns, should return last response even if loop isn't done."""
        loop = AgentLoop(agent_name="Test")
        # Always return tool call, never exit loop naturally
        mock_llm = MagicMock(return_value='SEARCH: "endless"')

        messages = [
            {"role": "system", "content": "sys"},
            {"role": "user", "content": "test"},
        ]

        result = await loop.execute(messages, call_llm_fn=mock_llm, max_turns=2)
        assert mock_llm.call_count == 2

    @pytest.mark.asyncio
    async def test_execute_with_context_guard(self):
        """Test that context guard functions are called."""
        loop = AgentLoop(agent_name="Test")
        mock_llm = MagicMock(return_value="Answer")
        check_fn = MagicMock(return_value=False)
        flush_fn = MagicMock()

        messages = [
            {"role": "system", "content": "sys"},
            {"role": "user", "content": "test"},
        ]

        await loop.execute(
            messages, call_llm_fn=mock_llm,
            check_context_fn=check_fn, flush_fn=flush_fn
        )
        check_fn.assert_called_once()
        flush_fn.assert_not_called()

    @pytest.mark.asyncio
    async def test_execute_triggers_flush(self):
        """Context guard returns True → flush should be called."""
        loop = AgentLoop(agent_name="Test")
        mock_llm = MagicMock(return_value="Answer")
        check_fn = MagicMock(return_value=True)
        flush_fn = MagicMock()

        messages = [
            {"role": "system", "content": "sys"},
            {"role": "user", "content": "test"},
        ]

        await loop.execute(
            messages, call_llm_fn=mock_llm,
            check_context_fn=check_fn, flush_fn=flush_fn
        )
        flush_fn.assert_called_once()


class TestAgentLoopParseToolCall:

    def test_parse_search(self):
        result = AgentLoop.parse_tool_call('Let me search. SEARCH: "AAPL"')
        assert result == [("SEARCH", {"query": "AAPL"})]

    def test_parse_call(self):
        result = AgentLoop.parse_tool_call('CALL: get_price({"ticker": "AAPL"})')
        assert result == [("get_price", {"ticker": "AAPL"})]

    def test_parse_call_invalid_json(self):
        result = AgentLoop.parse_tool_call("CALL: my_tool(some_text)")
        assert result == []

    def test_parse_no_tool(self):
        result = AgentLoop.parse_tool_call("Just a normal response with no tools.")
        assert result == []

    def test_parse_multiline(self):
        text = "Thinking...\nSEARCH: \"Tesla stock\"\nMore text"
        result = AgentLoop.parse_tool_call(text)
        assert result == [("SEARCH", {"query": "Tesla stock"})]

    @pytest.mark.asyncio
    async def test_tool_not_found(self):
        """Tool not in registry should return error observation."""
        loop = AgentLoop(agent_name="Test")
        result = await loop._execute_tool_async("unknown_tool", {"a": 1})
        assert "Error: Tool 'unknown_tool' not found." in result

    @pytest.mark.asyncio
    async def test_search_no_service(self):
        """SEARCH without service should return error."""
        loop = AgentLoop(agent_name="Test")
        result = await loop._run_tool_logic_async("SEARCH", {"query": "test"})
        assert "Error: Search service not initialized." in result
