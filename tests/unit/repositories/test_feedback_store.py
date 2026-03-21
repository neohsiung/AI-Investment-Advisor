import pytest
import uuid
from unittest.mock import MagicMock, patch
from src.data.feedback_store import FeedbackStore

class TestFeedbackStore:
    def test_init(self):
        store = FeedbackStore(db_path=":memory:")
        assert store.db_path == ":memory:"

    @patch('src.data.feedback_store.get_db_connection')
    def test_save_example(self, mock_get_conn):
        mock_conn = MagicMock()
        mock_get_conn.return_value = mock_conn
        
        store = FeedbackStore()
        store.save_example("test_agent", [0.1, 0.2], "response", 0.9, "context")
        
        mock_conn.execute.assert_called()
        mock_conn.commit.assert_called()
        mock_conn.close.assert_called()

    @patch('src.data.feedback_store.get_db_connection')
    def test_get_similar_examples(self, mock_get_conn):
        mock_conn = MagicMock()
        mock_get_conn.return_value = mock_conn
        mock_conn.execute.return_value.fetchall.return_value = [
            ("resp1", 0.9, 0.8, "ctx1")
        ]
        
        store = FeedbackStore()
        results = store.get_similar_examples("test_agent", [0.1, 0.2])
        
        assert len(results) == 1
        assert results[0]["response"] == "resp1"

    @patch('src.data.feedback_store.get_db_connection')
    def test_get_similar_examples_error(self, mock_get_conn):
        mock_conn = MagicMock()
        mock_get_conn.return_value = mock_conn
        mock_conn.execute.side_effect = Exception("error")
        
        store = FeedbackStore()
        results = store.get_similar_examples("test_agent", [0.1, 0.2])
        
        assert results == []

    @patch('src.data.feedback_store.get_db_connection')
    def test_get_examples_for_training(self, mock_get_conn):
        mock_conn = MagicMock()
        mock_get_conn.return_value = mock_conn
        mock_conn.execute.return_value.fetchall.return_value = [
            ("ctx1", "resp1", 0.9)
        ]
        
        store = FeedbackStore()
        results = store.get_examples_for_training("test_agent")
        
        assert len(results) == 1
        assert results[0]["context"] == "ctx1"

    @patch('src.data.feedback_store.get_db_connection')
    def test_get_examples_for_training_error(self, mock_get_conn):
        mock_conn = MagicMock()
        mock_get_conn.return_value = mock_conn
        mock_conn.execute.side_effect = Exception("error")
        
        store = FeedbackStore()
        results = store.get_examples_for_training("test_agent")
        
        assert results == []
