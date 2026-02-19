import pytest
import os
import json
from unittest.mock import MagicMock, patch
from sqlalchemy import create_engine
from src.repositories.agent_repository import AlchemyAgentRepository
from src.repositories.sentinel_repository import AlchemySentinelRepository

@pytest.fixture
def test_engine():
    # Use in-memory SQLite for repository testing (that supports generic SQL)
    engine = create_engine("sqlite:///:memory:")
    return engine

class TestAgentRepository:
    def test_init_and_weight(self, test_engine):
        repo = AlchemyAgentRepository(engine=test_engine)
        # Should initialize table and return default weight
        assert repo.get_agent_weight("non_existent") == 1.0
        
    def test_update_performance_and_top_agents(self, test_engine):
        repo = AlchemyAgentRepository(engine=test_engine)
        
        # Initial Update
        repo.update_performance("agent1", "tier1", success=True, latency=0.5, weight_delta=0.1)
        
        # Check Weight updated
        assert repo.get_agent_weight("agent1") == 1.1
        
        # Get Top Agents
        top = repo.get_top_agents("tier1")
        assert len(top) == 1
        assert top[0]["name"] == "agent1"
        assert top[0]["weight"] == 1.1
        
    def test_error_handling(self):
        # Mock engine that fails
        mock_engine = MagicMock()
        mock_engine.connect.side_effect = Exception("DB Fail")
        mock_engine.begin.side_effect = Exception("DB Fail")
        
        repo = AlchemyAgentRepository(engine=mock_engine)
        assert repo.get_agent_weight("any") == 1.0
        repo.update_performance("any", "tier", True) # Should just log error
        assert repo.get_top_agents("tier") == []

class TestSentinelRepository:
    @patch('src.repositories.sentinel_repository.get_db_engine')
    def test_init_and_alerts(self, mock_get_engine):
        mock_engine = MagicMock()
        mock_conn = mock_engine.connect.return_value.__enter__.return_value
        mock_begin = mock_engine.begin.return_value.__enter__.return_value
        
        repo = AlchemySentinelRepository(engine=mock_engine)
        
        # Log Alert
        repo.log_alert("Title", "Content", metadata={"key": "val"})
        mock_begin.execute.assert_called()
        
        # Check Duplicate
        mock_conn.execute.return_value.scalar.return_value = 1
        assert repo.is_duplicate_alert("Title", "Content") is True
        
    @patch('src.repositories.sentinel_repository.get_db_engine')
    def test_get_last_signal_value(self, mock_get_engine):
        mock_engine = MagicMock()
        mock_conn = mock_engine.connect.return_value.__enter__.return_value
        mock_conn.execute.return_value.scalar.return_value = 45.0
        
        repo = AlchemySentinelRepository(engine=mock_engine)
        val = repo.get_last_signal_value("vix")
        assert val == 45.0
        
    def test_error_handling_sentinel(self):
        mock_engine = MagicMock()
        mock_engine.connect.side_effect = Exception("DB Fail")
        mock_engine.begin.side_effect = Exception("DB Fail")
        
        repo = AlchemySentinelRepository(engine=mock_engine)
        repo.log_alert("Title", "Content") # Should not crash
        assert repo.is_duplicate_alert("Title", "Content") is False
        assert repo.get_last_signal_value("any") == 0.0

    @patch('src.repositories.sentinel_repository.get_db_engine')
    def test_threshold_methods(self, mock_get_engine):
        mock_engine = MagicMock()
        mock_conn = mock_engine.connect.return_value.__enter__.return_value
        mock_begin = mock_engine.begin.return_value.__enter__.return_value
        
        # Set up mock rows for get_all_thresholds
        mock_row = MagicMock()
        mock_row.key = "key1"
        mock_row.value = 10.5
        mock_conn.execute.return_value = [mock_row]
        
        repo = AlchemySentinelRepository(engine=mock_engine)
        
        # get_all_thresholds
        thresholds = repo.get_all_thresholds()
        assert thresholds == {"key1": 10.5}
        
        # update_threshold
        repo.update_threshold("key1", 11.0, "reviewer")
        mock_begin.execute.assert_called()
        
        # seed_defaults
        repo.seed_defaults({"key2": 20.0})
        # key1 exists, key2 doesn't. update_threshold should be called for key2.
        assert mock_begin.execute.call_count == 2
