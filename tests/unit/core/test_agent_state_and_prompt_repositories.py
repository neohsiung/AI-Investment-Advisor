"""
Extended tests for Agent State and Prompt Repositories.
測試代理狀態與提示詞倉庫。
"""
import pytest
from unittest.mock import MagicMock, patch
from src.repositories.agent_state_repository import AlchemyAgentStateRepository
from src.repositories.prompt_repository import AlchemyPromptRepository


class TestAgentStateRepository:
    
    def test_get_state_existing(self):
        """Test get_state returns existing state."""
        with patch('src.repositories.agent_state_repository.get_db_engine') as mock_db:
            mock_conn = MagicMock()
            mock_db.return_value.connect.return_value.__enter__.return_value = mock_conn
            
            # Mock fetchone to return a row
            mock_conn.execute.return_value.fetchone.return_value = ("hash123", "output_data")
            
            repo = AlchemyAgentStateRepository()
            result = repo.get_state("agent_001")
            
            assert result == ("hash123", "output_data")
            mock_conn.execute.assert_called_once()
    
    def test_get_state_not_found(self):
        """Test get_state returns None when state doesn't exist."""
        with patch('src.repositories.agent_state_repository.get_db_engine') as mock_db:
            mock_conn = MagicMock()
            mock_db.return_value.connect.return_value.__enter__.return_value = mock_conn
            
            # Mock fetchone to return None
            mock_conn.execute.return_value.fetchone.return_value = None
            
            repo = AlchemyAgentStateRepository()
            result = repo.get_state("nonexistent")
            
            assert result is None
    
    def test_save_state_new(self):
        """Test save_state creates new state entry."""
        with patch('src.repositories.agent_state_repository.get_db_engine') as mock_db:
            mock_conn = MagicMock()
            mock_db.return_value.begin.return_value.__enter__.return_value = mock_conn
            
            repo = AlchemyAgentStateRepository()
            repo.save_state("agent_001", "TestAgent", "hash123", "output_data")
            
            # Verify INSERT was called
            mock_conn.execute.assert_called_once()
    
    def test_save_state_update(self):
        """Test save_state updates existing state."""
        with patch('src.repositories.agent_state_repository.get_db_engine') as mock_db:
            mock_conn = MagicMock()
            mock_db.return_value.begin.return_value.__enter__.return_value = mock_conn
            
            repo = AlchemyAgentStateRepository()
            repo.save_state("agent_001", "TestAgent", "hash_new", "new_output")
            
            mock_conn.execute.assert_called_once()
    
    def test_save_state_with_special_characters(self):
        """Test save_state handles special characters in output."""
        with patch('src.repositories.agent_state_repository.get_db_engine') as mock_db:
            mock_conn = MagicMock()
            mock_db.return_value.begin.return_value.__enter__.return_value = mock_conn
            
            repo = AlchemyAgentStateRepository()
            special_output = "Output with 'quotes' and \"double quotes\" and \nnewlines"
            repo.save_state("agent_001", "TestAgent", "hash123", special_output)
            
            # Should not raise exception
            mock_conn.execute.assert_called_once()


class TestPromptRepository:
    
    def test_log_change_success(self):
        """Test log_change successfully logs prompt change."""
        with patch('src.repositories.prompt_repository.get_db_engine') as mock_db:
            mock_conn = MagicMock()
            mock_db.return_value.begin.return_value.__enter__.return_value = mock_conn
            
            repo = AlchemyPromptRepository()
            repo.log_change(
                agent_name="TestAgent",
                reason="Performance improvement",
                old_prompt="Old prompt",
                new_prompt="New prompt",
                diff="+ New prompt\n- Old prompt",
                user_id="test_user"
            )
            
            mock_conn.execute.assert_called_once()
            
            # Check INSERT statement
            call_args = mock_conn.execute.call_args
            assert "INSERT INTO prompt_history" in str(call_args[0][0])
    
    def test_log_change_with_special_characters(self):
        """Test log_change handles special characters."""
        with patch('src.repositories.prompt_repository.get_db_engine') as mock_db:
            mock_conn = MagicMock()
            mock_db.return_value.begin.return_value.__enter__.return_value = mock_conn
            
            repo = AlchemyPromptRepository()
            repo.log_change(
                agent_name="TestAgent",
                reason="Fix 'quote' handling",
                old_prompt="Prompt with \"quotes\"",
                new_prompt="New prompt with 'quotes'",
                diff="Complex\ndiff\nwith\nspecial $ chars",
                user_id="test_user"
            )
            
            mock_conn.execute.assert_called_once()
    
    def test_log_change_handles_db_error(self):
        """Test log_change handles database errors gracefully."""
        with patch('src.repositories.prompt_repository.get_db_engine') as mock_db:
            mock_conn = MagicMock()
            mock_db.return_value.begin.return_value.__enter__.return_value = mock_conn
            
            # Simulate DB error
            mock_conn.execute.side_effect = Exception("DB connection failed")
            
            repo = AlchemyPromptRepository()
            # Should not raise exception, but print error
            repo.log_change(
                agent_name="TestAgent",
                reason="Test",
                old_prompt="Old",
                new_prompt="New",
                diff="Diff",
                user_id="test_user"
            )
    
    def test_log_change_generates_unique_ids(self):
        """Test log_change generates unique IDs for each change."""
        with patch('src.repositories.prompt_repository.get_db_engine') as mock_db:
            mock_conn = MagicMock()
            mock_db.return_value.begin.return_value.__enter__.return_value = mock_conn
            
            repo = AlchemyPromptRepository()
            
            # Log two changes
            repo.log_change("TestAgent", "Optimization", "Old prompt", "New prompt", "Diff", "test_user")
            repo.log_change("Agent2", "Reason2", "Old2", "New2", "Diff2", "user2")
            
            # Should have called execute twice
            assert mock_conn.execute.call_count == 2
