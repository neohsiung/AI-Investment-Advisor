"""
Tests for HR 360 Feedback Repository (src/repositories/feedback_repository.py).
測試 HR 360 回饋倉儲。
"""
import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime
from src.repositories.feedback_repository import AlchemyFeedbackRepository

@pytest.fixture
def mock_engine():
    """Create a mock database engine."""
    engine = MagicMock()
    
    # Mock for SELECT operations (connect)
    mock_conn_read = MagicMock()
    engine.connect.return_value.__enter__.return_value = mock_conn_read
    
    # Mock for INSERT operations (begin)
    mock_conn_write = MagicMock()
    engine.begin.return_value.__enter__.return_value = mock_conn_write
    
    return engine, mock_conn_read, mock_conn_write

class TestAlchemyFeedbackRepository:
    
    def test_add_review_success(self, mock_engine):
        """Test adding a peer review."""
        engine, _, mock_conn_write = mock_engine
        repo = AlchemyFeedbackRepository(engine=engine)
        
        review_id = repo.add_review(
            reviewer="CIO",
            reviewee="Fundamental",
            score=4,
            comment="Good analysis",
            context_hash="abc123"
        )
        
        assert review_id is not None
        mock_conn_write.execute.assert_called_once()
    
    def test_add_review_without_context_hash(self, mock_engine):
        """Test adding review without context hash."""
        engine, _, mock_conn_write = mock_engine
        repo = AlchemyFeedbackRepository(engine=engine)
        
        review_id = repo.add_review(
            reviewer="Momentum",
            reviewee="CIO",
            score=5,
            comment="Excellent request"
        )
        
        assert review_id is not None
        mock_conn_write.execute.assert_called_once()
    
    def test_get_reviews_for_agent(self, mock_engine):
        """Test retrieving reviews received by an agent."""
        engine, mock_conn_read, _ = mock_engine
        mock_result = [
            MagicMock(_mapping={"id": "1", "reviewer": "CIO", "reviewee": "Fundamental", "score": 4})
        ]
        mock_conn_read.execute.return_value = mock_result
        
        repo = AlchemyFeedbackRepository(engine=engine)
        results = repo.get_reviews_for_agent("Fundamental")
        
        assert len(results) == 1
        mock_conn_read.execute.assert_called_once()
    
    def test_get_reviews_by_agent(self, mock_engine):
        """Test retrieving reviews given by an agent."""
        engine, mock_conn_read, _ = mock_engine
        mock_result = [
            MagicMock(_mapping={"id": "1", "reviewer": "CIO", "reviewee": "Macro", "score": 3})
        ]
        mock_conn_read.execute.return_value = mock_result
        
        repo = AlchemyFeedbackRepository(engine=engine)
        results = repo.get_reviews_by_agent("CIO")
        
        assert len(results) == 1
        mock_conn_read.execute.assert_called_once()
    
    def test_add_review_with_db_error(self, mock_engine):
        """Test error handling during add_review."""
        engine, _, mock_conn_write = mock_engine
        mock_conn_write.execute.side_effect = Exception("DB Error")
        
        repo = AlchemyFeedbackRepository(engine=engine)
        
        with pytest.raises(Exception) as exc_info:
            repo.add_review("CIO", "Fundamental", 4, "Test")
        
        assert "DB Error" in str(exc_info.value)
    
    def test_get_connection_default(self):
        """Test default connection retrieval."""
        with patch('src.repositories.feedback_repository.get_db_engine') as mock_get_engine:
            mock_get_engine.return_value = MagicMock()
            
            repo = AlchemyFeedbackRepository()
            assert repo.engine is not None
