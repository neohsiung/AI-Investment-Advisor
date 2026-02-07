import pytest
from unittest.mock import MagicMock, patch
from src.repositories.vector_repository import VectorRepository
import json

@pytest.fixture
def mock_db_conn():
    with patch('src.repositories.vector_repository.get_db_connection') as mock_conn:
        conn = mock_conn.return_value
        # Default to SQLite behavior mock
        conn.engine.url = 'sqlite:///test.db'
        yield conn

def test_add_memory(mock_db_conn):
    repo = VectorRepository()
    embedding = [0.1, 0.2, 0.3]
    metadata = {"key": "value"}
    
    repo.add_memory("u1", "news", "content", embedding, metadata)
    
    mock_db_conn.execute.assert_called()
    args, _ = mock_db_conn.execute.call_args
    sql = str(args[0])
    params = args[1]
    
    assert "INSERT INTO memory_embeddings" in sql
    assert params["uid"] == "u1"
    assert params["cat"] == "news"
    # Verify embedding format
    assert params["emb"] == str(embedding)
    assert json.loads(params["meta"]) == metadata

def test_search_memory_sqlite_skip(mock_db_conn):
    """Verify SQLite skips vector search."""
    repo = VectorRepository()
    mock_db_conn.engine.url = 'sqlite:///test.db'
    
    res = repo.search_memory("u1", [0.1])
    assert res == []

def test_search_memory_postgres(mock_db_conn):
    """Verify Postgres generates vector search query."""
    repo = VectorRepository()
    mock_db_conn.engine.url = 'postgresql://user:pass@host/db'
    
    # Mock result
    mock_row = MagicMock()
    # Access by index
    mock_row.__getitem__.side_effect = lambda x: {
        0: "id1",
        1: "content",
        2: "category",
        3: '{"meta": "data"}',
        4: 0.95
    }[x]
    
    mock_db_conn.execute.return_value.fetchall.return_value = [mock_row]
    
    res = repo.search_memory("u1", [0.1, 0.2])
    
    assert len(res) == 1
    assert res[0]["id"] == "id1"
    assert res[0]["similarity"] == 0.95
    
    # Verify Query
    args, _ = mock_db_conn.execute.call_args
    sql = str(args[0])
    assert "ORDER BY similarity DESC" in sql
    assert "<=>" in sql # PGVector operator

def test_add_council_minute(mock_db_conn):
    repo = VectorRepository()
    transcript = "A said B"
    consensus = "Do B"
    participants = ["A"]
    embedding = [0.1]
    
    repo.add_council_minute("sess1", "topic", participants, consensus, transcript, embedding)
    
    mock_db_conn.execute.assert_called()
    args, _ = mock_db_conn.execute.call_args
    sql = str(args[0])
    params = args[1]
    
    assert "INSERT INTO council_minutes" in sql
    assert params["sid"] == "sess1"
    assert json.loads(params["parts"]) == participants

def test_add_memory_error(mock_db_conn):
    repo = VectorRepository()
    mock_db_conn.execute.side_effect = Exception("DB Error")
    
    with pytest.raises(Exception):
        repo.add_memory("u1", "cat", "cont", [])
