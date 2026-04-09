import pytest
import json
from unittest.mock import AsyncMock, patch, MagicMock
from datetime import datetime, timedelta
from src.services.cognitive_memory_manager import CognitiveMemoryManager

@pytest.fixture
def mock_db_engine():
    with patch("src.services.cognitive_memory_manager.get_db_engine") as mock_get:
        engine = MagicMock()
        mock_get.return_value = engine
        yield engine

@pytest.fixture
def manager(mock_db_engine):
    with patch("src.services.cognitive_memory_manager.CognitiveMemoryManager._check_db_health", return_value=True):
        return CognitiveMemoryManager(user_id="test_user")

def test_archive_to_long_term(manager, mock_db_engine):
    """Test archiving medium-term memory to long-term vector storage."""
    
    # Mocking rows returned by the SELECT query
    mock_row = MagicMock()
    mock_row.id = 1
    mock_row.agent_name = "InsightAgent"
    mock_row.memory_type = "insight"
    mock_row.content = {"summary": "Stock is moving up"}
    mock_row.importance = 0.8
    mock_row.source_id = "src1"
    mock_row.created_at = datetime.now() - timedelta(days=31)
    
    mock_conn = MagicMock()
    mock_conn.execute.return_value.fetchall.return_value = [mock_row]
    mock_db_engine.begin.return_value.__enter__.return_value = mock_conn
    
    with patch("src.services.settings_service.SettingsService") as MockSettings, \
         patch("src.infrastructure.llm.llm_gateway.LLMGatewayFactory") as MockFactory, \
         patch("src.repositories.vector_repository.AlchemyVectorRepository") as MockVectorRepo:
         
        # Mock settings
        mock_settings = MockSettings.return_value
        mock_settings.get_all_settings.return_value = {"AI_PROVIDER": "Mock"}
        
        # Mock Gateway embedding
        mock_gateway = MockFactory.create.return_value
        mock_gateway.embed.return_value = [0.1, 0.2, 0.3]
        
        # Mock Vector Repo
        mock_vector_repo = MockVectorRepo.return_value
        
        count = manager.archive_to_long_term(days_old=30)
        
        assert count == 1
        mock_gateway.embed.assert_called_once()
        mock_vector_repo.add_memory.assert_called_once()
        
        # Verify it tries to delete from the origin table
        # conn.execute is called twice: once for SELECT, once for DELETE
        assert mock_conn.execute.call_count >= 2
        delete_call_args = mock_conn.execute.call_args_list[-1][0]
        assert "DELETE FROM cognitive_memories" in str(delete_call_args[0])

def test_search_historical_context(manager, mock_db_engine):
    """Test that active RAG retrieval uses the LLM to embed and searches Vector DB."""
    with patch("src.services.settings_service.SettingsService") as MockSettings, \
         patch("src.infrastructure.llm.llm_gateway.LLMGatewayFactory") as MockFactory, \
         patch("src.repositories.vector_repository.AlchemyVectorRepository") as MockVectorRepo:
         
        mock_gateway = MockFactory.create.return_value
        mock_gateway.embed.return_value = [0.1, 0.2, 0.3]
        
        mock_vector_repo = MockVectorRepo.return_value
        mock_vector_repo.search_memory.return_value = [{"content": "Historical data", "final_score": 0.95}]
        
        results = manager.search_historical_context("How did we trade AAPL?", limit=2)
        
        assert len(results) == 1
        assert results[0]["content"] == "Historical data"
        mock_gateway.embed.assert_called_once()
        args, _ = mock_gateway.embed.call_args
        assert args[0] == "How did we trade AAPL?"
        mock_vector_repo.search_memory.assert_called_once()
