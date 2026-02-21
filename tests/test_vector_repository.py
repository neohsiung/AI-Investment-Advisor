import pytest
import os
import json
from src.repositories.vector_repository import AlchemyVectorRepository
from src.data.database import init_db

@pytest.fixture
def repo(tmp_path):
    """Create a repo with a fresh in-memory DB."""
    db_path = str(tmp_path / "test_vector.db")
    init_db(db_path)
    return AlchemyVectorRepository(db_path=db_path)

def test_add_memory(repo):
    embedding = [0.1, 0.2, 0.3]
    metadata = {"key": "value"}
    
    mid = repo.add_memory("u1", "news", "content", embedding, metadata)
    assert mid is not None
    
    # Verify in DB
    with repo.engine.connect() as conn:
        from sqlalchemy import text
        row = conn.execute(text("SELECT * FROM memory_embeddings WHERE id = :id"), {"id": mid}).fetchone()
        assert row is not None
        # row._mapping['content'] for SQLAlchemy 1.4+
        r = row._mapping
        assert r['user_id'] == "u1"
        assert r['content'] == "content"
        assert json.loads(r['metadata']) == metadata
        assert r['embedding'] == str(embedding)

def test_search_memory_sqlite_fallback(repo):
    """Verify SQLite skips vector search and returns empty list gracefully."""
    res = repo.search_memory("u1", [0.1, 0.2, 0.3])
    assert res == []

def test_add_council_minute(repo):
    transcript = "A said B"
    consensus = "Do B"
    participants = ["A"]
    embedding = [0.1]
    
    mid = repo.add_council_minute("u1", "sess1", "topic", participants, consensus, transcript, embedding)
    assert mid is not None
    
    with repo.engine.connect() as conn:
        from sqlalchemy import text
        row = conn.execute(text("SELECT * FROM council_minutes WHERE id = :id"), {"id": mid}).fetchone()
        assert row is not None
        r = row._mapping
        assert r['session_id'] == "sess1"
        assert r['consensus'] == consensus
        assert r['embedding'] == str(embedding)

def test_search_similar_minutes_sqlite_fallback(repo):
    res = repo.search_similar_minutes_by_embedding([0.1], limit=1)
    assert res == []
