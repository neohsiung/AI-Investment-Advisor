"""
Tests for Phase 5: Three-Tier Memory Architecture.
Phase 5 測試：三層記憶體架構。
"""

import pytest
import json
import os
import tempfile
from unittest.mock import MagicMock, patch

from src.infrastructure.memory.three_tier_memory import (
    IWorkingMemory, ISessionStorage, ILongTermMemory,
    InMemoryWorkingMemory, FileSessionStorage, HybridMemoryAdapter,
    ThreeTierMemory,
)


# ──────────────────────────────────────────────────────
# Tier 1: Working Memory Tests
# ──────────────────────────────────────────────────────

class TestInMemoryWorkingMemory:

    def test_add_and_get_messages(self):
        wm = InMemoryWorkingMemory()
        wm.add_message("user", "Hello")
        wm.add_message("assistant", "Hi there!")
        msgs = wm.get_messages()
        assert len(msgs) == 2
        assert msgs[0] == {"role": "user", "content": "Hello"}
        assert msgs[1] == {"role": "assistant", "content": "Hi there!"}

    def test_clear(self):
        wm = InMemoryWorkingMemory()
        wm.add_message("user", "test")
        wm.set_scratchpad("key", "value")
        wm.clear()
        assert len(wm.get_messages()) == 0
        assert wm.get_scratchpad() == {}

    def test_scratchpad(self):
        wm = InMemoryWorkingMemory()
        wm.set_scratchpad("ticker", "AAPL")
        wm.set_scratchpad("amount", 100)
        sp = wm.get_scratchpad()
        assert sp["ticker"] == "AAPL"
        assert sp["amount"] == 100

    def test_scratchpad_returns_copy(self):
        wm = InMemoryWorkingMemory()
        wm.set_scratchpad("key", "val")
        sp = wm.get_scratchpad()
        sp["key"] = "modified"
        assert wm.get_scratchpad()["key"] == "val"  # original unchanged

    def test_estimate_tokens(self):
        wm = InMemoryWorkingMemory()
        wm.add_message("user", "A" * 400)  # ~100 tokens
        wm.add_message("assistant", "B" * 200)  # ~50 tokens
        assert wm.estimate_tokens() == 150

    def test_estimate_tokens_empty(self):
        wm = InMemoryWorkingMemory()
        assert wm.estimate_tokens() == 0

    def test_truncate_to_checkpoint(self):
        wm = InMemoryWorkingMemory()
        wm.add_message("system", "You are an agent")
        wm.add_message("user", "Old message 1")
        wm.add_message("assistant", "Old response")
        wm.add_message("user", "Old message 2")

        system_msg = {"role": "system", "content": "You are an agent"}
        wm.truncate_to_checkpoint(system_msg, "WAL checkpoint state")

        msgs = wm.get_messages()
        assert len(msgs) == 2
        assert msgs[0]["role"] == "system"
        assert "WAL checkpoint state" in msgs[1]["content"]

    def test_implements_interface(self):
        wm = InMemoryWorkingMemory()
        assert isinstance(wm, IWorkingMemory)


# ──────────────────────────────────────────────────────
# Tier 2: Session Storage Tests
# ──────────────────────────────────────────────────────

class TestFileSessionStorage:

    @pytest.fixture
    def storage_dir(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            yield tmpdir

    def test_save_and_load_checkpoint(self, storage_dir):
        ss = FileSessionStorage(workspace_path=storage_dir)
        state = {"messages_count": 10, "last_tool": "search_web"}
        ss.save_checkpoint("sess-001", state)
        loaded = ss.load_checkpoint("sess-001")
        assert loaded["session_id"] == "sess-001"
        assert loaded["messages_count"] == 10

    def test_load_missing_checkpoint(self, storage_dir):
        ss = FileSessionStorage(workspace_path=storage_dir)
        assert ss.load_checkpoint("nonexistent") is None

    def test_save_and_load_wal(self, storage_dir):
        ss = FileSessionStorage(workspace_path=storage_dir)
        ss.save_wal("TestAgent", "WAL: Current state is analyzing AAPL")
        wal = ss.load_wal("TestAgent")
        assert "WAL: Current state is analyzing AAPL" in wal
        assert "Session Checkpoint" in wal

    def test_load_missing_wal(self, storage_dir):
        ss = FileSessionStorage(workspace_path=storage_dir)
        assert ss.load_wal("Missing") is None

    def test_overwrite_wal(self, storage_dir):
        ss = FileSessionStorage(workspace_path=storage_dir)
        ss.save_wal("Agent", "state_v1")
        ss.save_wal("Agent", "state_v2")
        wal = ss.load_wal("Agent")
        assert "state_v2" in wal
        assert "state_v1" not in wal

    def test_implements_interface(self, storage_dir):
        ss = FileSessionStorage(workspace_path=storage_dir)
        assert isinstance(ss, ISessionStorage)


# ──────────────────────────────────────────────────────
# Tier 3: Long-Term Memory Adapter Tests
# ──────────────────────────────────────────────────────

class TestHybridMemoryAdapter:

    def test_store_delegates(self):
        mock_hm = MagicMock()
        mock_hm.add_memory.return_value = "mem-123"
        adapter = HybridMemoryAdapter(hybrid_memory=mock_hm)

        result = adapter.store("user1", "AAPL looks bullish", metadata={"category": "analysis"})
        assert result == "mem-123"
        mock_hm.add_memory.assert_called_once_with(
            user_id="user1", content="AAPL looks bullish",
            embedding=[], metadata={"category": "analysis"}
        )

    def test_search_delegates(self):
        mock_hm = MagicMock()
        mock_hm.search.return_value = [{"content": "AAPL analysis", "score": 0.9}]
        adapter = HybridMemoryAdapter(hybrid_memory=mock_hm)

        results = adapter.search(query_text="AAPL", user_id="user1", limit=3)
        assert len(results) == 1
        mock_hm.search.assert_called_once()

    def test_inner_property(self):
        mock_hm = MagicMock()
        adapter = HybridMemoryAdapter(hybrid_memory=mock_hm)
        assert adapter.inner is mock_hm

    def test_implements_interface(self):
        mock_hm = MagicMock()
        adapter = HybridMemoryAdapter(hybrid_memory=mock_hm)
        assert isinstance(adapter, ILongTermMemory)


# ──────────────────────────────────────────────────────
# ThreeTierMemory Composite Tests
# ──────────────────────────────────────────────────────

class TestThreeTierMemory:

    @pytest.fixture
    def workspace(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            yield tmpdir

    def test_default_construction(self, workspace):
        mock_hm = MagicMock()
        mem = ThreeTierMemory(
            longterm=HybridMemoryAdapter(hybrid_memory=mock_hm),
            workspace_path=workspace
        )
        assert isinstance(mem.working, InMemoryWorkingMemory)
        assert isinstance(mem.session, FileSessionStorage)
        assert isinstance(mem.longterm, HybridMemoryAdapter)

    def test_custom_tiers(self):
        wm = MagicMock(spec=IWorkingMemory)
        ss = MagicMock(spec=ISessionStorage)
        lt = MagicMock(spec=ILongTermMemory)
        mem = ThreeTierMemory(working=wm, session=ss, longterm=lt)
        assert mem.working is wm
        assert mem.session is ss
        assert mem.longterm is lt

    def test_flush_working_to_session(self, workspace):
        mock_hm = MagicMock()
        mem = ThreeTierMemory(
            longterm=HybridMemoryAdapter(hybrid_memory=mock_hm),
            workspace_path=workspace
        )
        mem.flush_working_to_session("TestAgent", "WAL: reasoning about TSLA")
        wal = mem.session.load_wal("TestAgent")
        assert "WAL: reasoning about TSLA" in wal

    def test_restore_from_session(self, workspace):
        mock_hm = MagicMock()
        mem = ThreeTierMemory(
            longterm=HybridMemoryAdapter(hybrid_memory=mock_hm),
            workspace_path=workspace
        )
        # First, save a WAL
        mem.session.save_wal("TestAgent", "Previous state: analyzing AAPL")
        # Add some old messages
        mem.working.add_message("system", "You are an agent")
        mem.working.add_message("user", "old")

        # Then restore
        system_msg = {"role": "system", "content": "You are an agent"}
        restored = mem.restore_from_session("TestAgent", system_msg)
        assert restored is True
        msgs = mem.working.get_messages()
        assert len(msgs) == 2
        assert "Previous state: analyzing AAPL" in msgs[1]["content"]

    def test_restore_no_wal(self, workspace):
        mock_hm = MagicMock()
        mem = ThreeTierMemory(
            longterm=HybridMemoryAdapter(hybrid_memory=mock_hm),
            workspace_path=workspace
        )
        restored = mem.restore_from_session("NoAgent", {"role": "system", "content": "x"})
        assert restored is False

    def test_end_to_end_flow(self, workspace):
        """Simulate: add messages → flush → restore."""
        mock_hm = MagicMock()
        mem = ThreeTierMemory(
            longterm=HybridMemoryAdapter(hybrid_memory=mock_hm),
            workspace_path=workspace
        )

        # Step 1: Add messages
        mem.working.add_message("system", "You are CIO")
        mem.working.add_message("user", "Analyze AAPL")
        mem.working.add_message("assistant", "AAPL shows bullish momentum")
        assert mem.working.estimate_tokens() > 0

        # Step 2: Flush
        mem.flush_working_to_session("CIO", "WAL: AAPL is bullish, pending risk review")

        # Step 3: Restore
        sys_msg = {"role": "system", "content": "You are CIO"}
        mem.restore_from_session("CIO", sys_msg)
        msgs = mem.working.get_messages()
        assert len(msgs) == 2
        assert "pending risk review" in msgs[1]["content"]
