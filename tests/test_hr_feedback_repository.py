"""
Tests for HR 360 Feedback Repository (src/repositories/feedback_repository.py).
測試 HR 360 回饋倉儲。
"""
import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime
from src.repositories.feedback_repository import SqliteFeedbackRepository

@pytest.fixture
def mock_connection():
    """Create a mock database connection."""
    conn = MagicMock()
    conn.execute.return_value = MagicMock()
    return conn

class TestSqliteFeedbackRepository:
    
    def test_add_review_success(self, mock_connection):
        """Test adding a peer review."""
        repo = SqliteFeedbackRepository(connection=mock_connection)
        
        review_id = repo.add_review(
            reviewer="CIO",
            reviewee="Fundamental",
            score=4,
            comment="Good analysis",
            context_hash="abc123"
        )
        
        assert review_id is not None
        mock_connection.execute.assert_called_once()
        # Should NOT commit when using injected connection
        mock_connection.commit.assert_not_called()
    
    def test_add_review_without_context_hash(self, mock_connection):
        """Test adding review without context hash."""
        repo = SqliteFeedbackRepository(connection=mock_connection)
        
        review_id = repo.add_review(
            reviewer="Momentum",
            reviewee="CIO",
            score=5,
            comment="Excellent request"
        )
        
        assert review_id is not None
        mock_connection.execute.assert_called_once()
    
    def test_get_reviews_for_agent(self, mock_connection):
        """Test retrieving reviews received by an agent."""
        mock_result = [
            MagicMock(_mapping={"id": "1", "reviewer": "CIO", "reviewee": "Fundamental", "score": 4})
        ]
        mock_connection.execute.return_value = mock_result
        
        repo = SqliteFeedbackRepository(connection=mock_connection)
        results = repo.get_reviews_for_agent("Fundamental")
        
        assert len(results) == 1
        mock_connection.execute.assert_called_once()
    
    def test_get_reviews_by_agent(self, mock_connection):
        """Test retrieving reviews given by an agent."""
        mock_result = [
            MagicMock(_mapping={"id": "1", "reviewer": "CIO", "reviewee": "Macro", "score": 3})
        ]
        mock_connection.execute.return_value = mock_result
        
        repo = SqliteFeedbackRepository(connection=mock_connection)
        results = repo.get_reviews_by_agent("CIO")
        
        assert len(results) == 1
        mock_connection.execute.assert_called_once()
    
    def test_add_review_with_db_error(self, mock_connection):
        """Test error handling during add_review."""
        mock_connection.execute.side_effect = Exception("DB Error")
        
        repo = SqliteFeedbackRepository(connection=mock_connection)
        
        with pytest.raises(Exception) as exc_info:
            repo.add_review("CIO", "Fundamental", 4, "Test")
        
        assert "DB Error" in str(exc_info.value)
    
    def test_get_connection_default(self):
        """Test default connection retrieval."""
        with patch('src.repositories.feedback_repository.get_db_connection') as mock_get_conn:
            mock_get_conn.return_value = MagicMock()
            
            repo = SqliteFeedbackRepository()
            conn = repo.get_connection()
            
            mock_get_conn.assert_called_once()
            assert conn is not None
