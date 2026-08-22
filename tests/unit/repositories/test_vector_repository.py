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


# ──────────────────────────────────────────────────────────────────────
# 2026-07-14: k=1 -> k=5 + recency-weighted scoring + user_id isolation.
# The sqlite fixture above can't exercise the real pgvector SQL (it
# early-returns for sqlite), so these use a mocked "postgresql" engine to
# verify the query text and bound parameters directly.
# ──────────────────────────────────────────────────────────────────────

from unittest.mock import MagicMock, patch


def _postgres_repo():
    engine = MagicMock()
    engine.dialect.name = "postgresql"
    conn = MagicMock()
    engine.connect.return_value.__enter__.return_value = conn
    repo = AlchemyVectorRepository(engine=engine)
    return repo, conn


class TestSimilarMinutesUserIsolationAndRecall:
    def test_embedding_search_defaults_to_k5(self):
        repo, conn = _postgres_repo()
        conn.execute.return_value.fetchall.return_value = []

        repo.search_similar_minutes_by_embedding([0.1, 0.2], user_id="user-a")

        params = conn.execute.call_args[0][1]
        assert params["limit"] == 5

    def test_embedding_search_filters_by_user_id(self):
        repo, conn = _postgres_repo()
        conn.execute.return_value.fetchall.return_value = []

        repo.search_similar_minutes_by_embedding([0.1, 0.2], user_id="user-a", limit=3)

        query_text = str(conn.execute.call_args[0][0])
        params = conn.execute.call_args[0][1]
        assert "user_id = :uid" in query_text
        assert params["uid"] == "user-a"

    def test_embedding_search_omits_user_filter_when_none(self):
        """Explicit backward-compat escape hatch — must not silently scope
        to a nonexistent user; only pass user_id=None deliberately."""
        repo, conn = _postgres_repo()
        conn.execute.return_value.fetchall.return_value = []

        repo.search_similar_minutes_by_embedding([0.1, 0.2], user_id=None)

        query_text = str(conn.execute.call_args[0][0])
        assert "user_id = :uid" not in query_text

    def test_embedding_search_scores_blend_similarity_and_recency(self):
        repo, conn = _postgres_repo()
        conn.execute.return_value.fetchall.return_value = []

        repo.search_similar_minutes_by_embedding([0.1, 0.2], user_id="user-a")

        query_text = str(conn.execute.call_args[0][0])
        assert "0.7 *" in query_text
        assert "0.3 *" in query_text
        assert "ORDER BY score DESC" in query_text

    def test_embedding_search_returns_score_and_created_at(self):
        repo, conn = _postgres_repo()
        row = MagicMock(id="m1", topic="AAPL debate", consensus="BUY", similarity=0.9, score=0.85, created_at="2026-07-01")
        conn.execute.return_value.fetchall.return_value = [row]

        results = repo.search_similar_minutes_by_embedding([0.1, 0.2], user_id="user-a")

        assert results[0]["score"] == 0.85
        assert results[0]["created_at"] == "2026-07-01"

    def test_text_search_defaults_to_k5_and_filters_by_user(self):
        repo, conn = _postgres_repo()
        conn.execute.return_value.fetchall.return_value = []

        repo.search_similar_minutes("AAPL earnings", user_id="user-b")

        query_text = str(conn.execute.call_args[0][0])
        params = conn.execute.call_args[0][1]
        assert params["limit"] == 5
        assert params["uid"] == "user-b"
        assert "user_id = :uid" in query_text
