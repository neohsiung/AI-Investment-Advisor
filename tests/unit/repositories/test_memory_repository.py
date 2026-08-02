
import pytest
from unittest.mock import MagicMock, patch
from src.repositories.memory_repository import AlchemyMemoryRepository
from src.services.memory_service import ReportMemoryItem

@pytest.fixture
def mock_engine():
    mock_engine = MagicMock()
    mock_conn = MagicMock()
    # Mock engine.connect() context manager
    mock_engine.connect.return_value.__enter__.return_value = mock_conn
    # Mock engine.begin() context manager
    mock_engine.begin.return_value.__enter__.return_value = mock_conn
    return mock_engine, mock_conn

def test_save_report(mock_engine):
    engine, conn = mock_engine
    repo = AlchemyMemoryRepository(engine=engine)
    
    item = ReportMemoryItem(
        user_id="user123",
        report_type="daily",
        report_date="2026-01-01",
        full_content="Today is a good day.",
        compressed_summary="Good day."
    )
    
    repo.save_report(item)
    
    # Verify execute was called
    assert conn.execute.called
    args, kwargs = conn.execute.call_args
    params = kwargs.get('parameters') or args[1]
    
    assert params["uid"] == "user123"
    assert params["content"] == "Today is a good day."
    assert params["rtype"] == "daily"

def test_get_recent_reports(mock_engine):
    engine, conn = mock_engine
    repo = AlchemyMemoryRepository(engine=engine)
    
    # Mock return rows
    mock_row = MagicMock()
    mock_row.user_id = "user123"
    mock_row.report_type = "daily"
    mock_row.date = "2026-01-02"
    mock_row.content = "Newer report"
    mock_row.summary = "Short Summary 1"
    
    conn.execute.return_value.fetchall.return_value = [mock_row]
    
    items = repo.get_recent_reports("user123", "daily", limit=5)
    
    assert len(items) == 1
    assert items[0].user_id == "user123"
    assert items[0].full_content == "Newer report"
    
    # Verify SQL params
    args, kwargs = conn.execute.call_args
    params = kwargs.get('parameters') or args[1]
    assert params["uid"] == "user123"
    assert params["limit"] == 5

def test_save_report_error_handling(mock_engine):
    engine, conn = mock_engine
    repo = AlchemyMemoryRepository(engine=engine)
    conn.execute.side_effect = Exception("DB Error")
    
    item = ReportMemoryItem(
        user_id="u", report_type="t", report_date="d", full_content="c"
    )
    
    # AlchemyMemoryRepository uses engine.begin(), it will raise if execute fails
    with pytest.raises(Exception):
        repo.save_report(item)

def test_get_recent_reports_error_handling(mock_engine):
    engine, conn = mock_engine
    repo = AlchemyMemoryRepository(engine=engine)
    conn.execute.side_effect = Exception("DB Error")

    with pytest.raises(Exception):
        repo.get_recent_reports("u", "t", 10)


# ──────────────────────────────────────────────────────────────────────
# AgentState: Postgres-primary storage (2026-07-14)
#
# agent_rules is now the source of truth for General Rules, per-user
# isolated — the old implementation kept rules ONLY in
# workspace/{agent}/STATE.md, keyed purely by agent_name with no user_id
# at all, so rules leaked across every tenant sharing a self-host
# instance. STATE.md is now a write-through render cache only.
# ──────────────────────────────────────────────────────────────────────

from src.repositories.memory_repository import AgentState


class TestAgentStatePostgresPrimary:
    def test_load_reads_from_db_when_row_exists(self, tmp_path, mock_engine):
        engine, conn = mock_engine
        # 2026-07-14 (B-P2.1): load_general_rules now aggregates ALL active
        # rows (fetchall), not just one (fetchone) — multiple atomic rules
        # per agent are now expected.
        conn.execute.return_value.fetchall.return_value = [("- DB rule for Macro",)]
        mgr = AgentState(workspace_root=str(tmp_path))

        with patch("src.data.database.get_db_engine", return_value=engine):
            result = mgr.load_general_rules("Macro", user_id="user-a")

        assert result == "- DB rule for Macro"
        params = conn.execute.call_args[0][1]
        assert params == {"uid": "user-a", "name": "Macro"}

    def test_different_users_get_different_rules(self, tmp_path, mock_engine):
        """The pre-migration bug: rules had no user_id and leaked across tenants."""
        engine, conn = mock_engine
        mgr = AgentState(workspace_root=str(tmp_path))

        def fake_execute(query, params):
            result = MagicMock()
            result.fetchall.return_value = [(f"- rule for {params['uid']}",)]
            return result
        conn.execute.side_effect = fake_execute

        with patch("src.data.database.get_db_engine", return_value=engine):
            rules_a = mgr.load_general_rules("Macro", user_id="user-a")
            rules_b = mgr.load_general_rules("Macro", user_id="user-b")

        assert rules_a == "- rule for user-a"
        assert rules_b == "- rule for user-b"
        assert rules_a != rules_b

    def test_save_supersedes_previous_active_row_then_inserts(self, tmp_path, mock_engine):
        engine, conn = mock_engine
        conn.execute.return_value.fetchone.return_value = (0,)  # MAX(version) subquery
        mgr = AgentState(workspace_root=str(tmp_path))

        with patch("src.data.database.get_db_engine", return_value=engine):
            mgr.save_general_rules("Macro", "- new rule", user_id="user-a")

        calls = conn.execute.call_args_list
        assert len(calls) == 2
        supersede_sql = str(calls[0][0][0])
        insert_sql = str(calls[1][0][0])
        assert "UPDATE agent_rules" in supersede_sql and "superseded" in supersede_sql
        assert "INSERT INTO agent_rules" in insert_sql
        assert calls[0][0][1] == {"uid": "user-a", "name": "Macro"}
        assert calls[1][0][1] == {"uid": "user-a", "name": "Macro", "rules": "- new rule"}

    def test_load_falls_back_to_state_md_when_db_unavailable(self, tmp_path):
        mgr = AgentState(workspace_root=str(tmp_path))
        path = mgr.get_state_path("Macro")
        import os
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            f.write("# STATE\n\n## General Rules\n- file-only rule\n")

        with patch("src.data.database.get_db_engine", side_effect=Exception("db down")):
            result = mgr.load_general_rules("Macro", user_id="user-a")

        assert result == "- file-only rule"

    def test_save_still_writes_state_md_even_if_db_write_fails(self, tmp_path):
        mgr = AgentState(workspace_root=str(tmp_path))

        with patch("src.data.database.get_db_engine", side_effect=Exception("db down")):
            mgr.save_general_rules("Macro", "- resilient rule", user_id="user-a")

        path = mgr.get_state_path("Macro")
        with open(path) as f:
            content = f.read()
        assert "## General Rules" in content
        assert "- resilient rule" in content

    def test_default_user_id_is_system_when_omitted(self, tmp_path, mock_engine):
        """Callers that haven't been updated to pass user_id must not crash."""
        engine, conn = mock_engine
        conn.execute.return_value.fetchall.return_value = []
        mgr = AgentState(workspace_root=str(tmp_path))

        with patch("src.data.database.get_db_engine", return_value=engine):
            mgr.load_general_rules("Macro")

        params = conn.execute.call_args[0][1]
        assert params["uid"] == "system"


class TestAgentStateAtomicRules:
    """
    2026-07-14 (B-P2.1): add_rule() inserts ONE atomic rule row without
    touching other active rules — unlike save_general_rules, which
    replaces the entire active set. Required for per-rule citation.
    """

    def test_add_rule_inserts_without_superseding_others(self, tmp_path, mock_engine):
        engine, conn = mock_engine
        conn.execute.return_value.fetchone.return_value = (42,)
        conn.execute.return_value.fetchall.return_value = [("- rule text",)]
        mgr = AgentState(workspace_root=str(tmp_path))

        with patch("src.data.database.get_db_engine", return_value=engine):
            new_id = mgr.add_rule("Macro", "- rule text", user_id="user-a", source_decision_id="dec-1")

        assert new_id == 42
        insert_sql = str(conn.execute.call_args_list[0][0][0])
        assert "INSERT INTO agent_rules" in insert_sql
        assert "UPDATE agent_rules SET status = 'superseded'" not in insert_sql
        insert_params = conn.execute.call_args_list[0][0][1]
        assert insert_params["source_decision_id"] == "dec-1"

    def test_add_rule_appends_to_file_when_db_unavailable(self, tmp_path):
        mgr = AgentState(workspace_root=str(tmp_path))
        # Seed prior file content directly (simulating an earlier successful save)
        path = mgr.get_state_path("Macro")
        import os
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            f.write("# STATE\n\n## General Rules\n- old rule\n")

        with patch("src.data.database.get_db_engine", side_effect=Exception("db down")):
            mgr.add_rule("Macro", "- new rule", user_id="user-a")

        with open(path) as f:
            content = f.read()
        # The pre-fix bug: DB-down fallback re-read from the (also-down) DB
        # and wrote an EMPTY string, destroying "- old rule".
        assert "- old rule" in content
        assert "- new rule" in content

    def test_get_active_rules_returns_id_text_score(self, tmp_path, mock_engine):
        engine, conn = mock_engine
        conn.execute.return_value.fetchall.return_value = [(1, "- rule A", 0.5), (2, "- rule B", -1.2)]
        mgr = AgentState(workspace_root=str(tmp_path))

        with patch("src.data.database.get_db_engine", return_value=engine):
            rules = mgr.get_active_rules("Macro", user_id="user-a")

        assert rules == [
            {"id": 1, "rule_text": "- rule A", "score": 0.5},
            {"id": 2, "rule_text": "- rule B", "score": -1.2},
        ]

    def test_get_active_rules_returns_empty_list_on_db_failure(self, tmp_path):
        """Citation/curation is a pure enhancement — never falls back to
        STATE.md (there's no per-rule id in a flat file)."""
        mgr = AgentState(workspace_root=str(tmp_path))
        with patch("src.data.database.get_db_engine", side_effect=Exception("db down")):
            rules = mgr.get_active_rules("Macro", user_id="user-a")
        assert rules == []
