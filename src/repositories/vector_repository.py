from src.utils.logger import setup_logger
logger = setup_logger("VectorRepository")

import uuid
import json
from abc import ABC, abstractmethod
import typing
from typing import List, Dict, Tuple, Any, Optional, Callable
from datetime import datetime
from sqlalchemy import text
from src.data.database import BaseRepository, get_db_engine

class IVectorRepository(ABC):
    """
    Interface for Vector Repository.
    向量儲存庫介面。
    """
    @abstractmethod
    def add_memory(self, user_id: str, category: str, content: str, embedding: List[float], metadata: Dict = {}) -> str:
        """
        Inserts a new memory item with vector embedding.
        新增帶有向量嵌入的記憶項目。
        """
        pass

    @abstractmethod
    def search_memory(self, user_id: str, embedding: List[float], top_k: int = 5, threshold: float = 0.7) -> List[Dict]:
        """
        Searches similar memories using vector similarity.
        使用向量相似度搜尋相似記憶。
        """
        pass

    @abstractmethod
    def add_council_minute(self, user_id: str, session_id: str, topic: str, participants: List[str], consensus: str, transcript: str, embedding: List[float]) -> str:
        """
        Logs a Council Session with vector embedding.
        記錄帶有向量嵌入的議會會議記錄。
        """
        pass

    @abstractmethod
    def search_similar_minutes(self, topic: str, user_id: Optional[str] = None, limit: int = 5) -> List[Dict]:
        """
        Retrieves past council minutes based on topic text similarity.
        `user_id` is optional only for backward compatibility with legacy
        callers; new call sites must pass it — omitting it searches across
        every tenant's minutes.
        """
        pass

    @abstractmethod
    def search_similar_minutes_by_embedding(self, embedding: List[float], user_id: Optional[str] = None, limit: int = 5, threshold: float = 0.7) -> List[Dict]:
        """
        Retrieves past council minutes based on embedding similarity,
        ranked by a recency-weighted score (0.7*cosine + 0.3*recency decay).
        根據嵌入相似度＋時間衰減混合分數檢索過去的議會記錄。
        `user_id` is optional only for backward compatibility; omitting it
        searches across every tenant's minutes (pre-2026-07-14 behavior).
        """
        pass

    @abstractmethod
    def list_minutes(self, user_id: str, limit: int = 20) -> List[Dict]:
        """List recent council minutes (id/topic/consensus preview/created_at), newest first."""
        pass

    @abstractmethod
    def get_minute(self, minute_id: str) -> Optional[Dict]:
        """Fetch a single council minute in full (topic/consensus/transcript)."""
        pass

class AlchemyVectorRepository(BaseRepository, IVectorRepository):
    """
    Repository for handling Vector Database operations (PGVector strictly).
    處理向量資料庫呈現 (PGVector 專用) 的儲存庫。
    """
    def __init__(self, db_path: str = None, engine: Any = None):
        """
        Initialize the repository.
        初始化儲存庫。
        """
        engine = engine or get_db_engine(db_path)
        BaseRepository.__init__(self, engine)

    def _ensure_string_embedding(self, embedding: List[float]) -> str:
        """
        Converts list to string format '[x,y,z]' for SQL insertion.
        將列表轉換為字串格式以供 SQL 插入。
        """
        return str(embedding)

    def add_memory(self, user_id: str, category: str, content: str, embedding: List[float], metadata: Dict = {}) -> str:
        """
        Inserts a new memory item with vector embedding.
        新增帶有向量嵌入的記憶項目。
        """
        new_id = str(uuid.uuid4())
        with self.engine.begin() as conn:
            query = text("""
                INSERT INTO memory_embeddings (id, user_id, content, embedding, metadata, created_at)
                VALUES (:id, :uid, :cont, :emb, :meta, :ts)
            """)
            
            conn.execute(query, {
                "id": new_id,
                "uid": user_id,
                "cont": content,
                "emb": self._ensure_string_embedding(embedding),
                "meta": json.dumps(metadata),
                "ts": datetime.utcnow()
            })
            return new_id

    def search_memory(self, user_id: str, embedding: List[float], query_text: str = "", top_k: int = 5, threshold: float = 0.7) -> List[Dict]:
        """
        Searches similar memories using vector similarity and BM25 (PostgreSQL pgvector + Search).
        """
        if self.engine.dialect.name == "sqlite":
            logger.warning("Vector search skipped on SQLite.")
            return []

        with self.engine.connect() as conn:
            sql = """
                WITH vector_scores AS (
                    SELECT 
                        id, 
                        content, 
                        metadata, 
                        1 - (embedding <=> :emb) as vector_score,
                        created_at
                    FROM memory_embeddings
                    WHERE user_id = :uid
                ),
                text_scores AS (
                    SELECT 
                        id,
                        (CASE WHEN :qtext = '' THEN 0 ELSE ts_rank(to_tsvector('simple', content), plainto_tsquery('simple', :qtext)) END) as text_score
                    FROM memory_embeddings
                    WHERE user_id = :uid
                ),
                max_text AS (
                    SELECT NULLIF(MAX(text_score), 0) as max_score FROM text_scores
                )
                SELECT 
                    v.id, 
                    v.content, 
                    v.metadata,
                    exp(-1 * EXTRACT(EPOCH FROM (NOW() - v.created_at)) / (86400 * 30)) as decay_factor,
                    v.vector_score,
                    COALESCE(t.text_score / m.max_score, 0) as norm_text_score,
                    (0.7 * v.vector_score + 0.3 * COALESCE(t.text_score / m.max_score, 0)) * 
                    exp(-1 * EXTRACT(EPOCH FROM (NOW() - v.created_at)) / (86400 * 30)) as final_score
                FROM vector_scores v
                JOIN text_scores t ON v.id = t.id
                CROSS JOIN max_text m
                WHERE v.vector_score > :threshold
                ORDER BY final_score DESC
                LIMIT :limit
            """
            
            query = text(sql)
            
            rows = conn.execute(query, {
                "uid": user_id,
                "emb": self._ensure_string_embedding(embedding),
                "qtext": query_text,
                "threshold": threshold,
                "limit": top_k * 2
            }).fetchall()
            
            results = []
            selected_ids = set()
            
            for row in rows:
                if len(results) >= top_k:
                    break
                if row.id not in selected_ids:
                    results.append({
                        "id": row.id,
                        "content": row.content,
                        "metadata": json.loads(row.metadata) if row.metadata else {},
                        "similarity": float(row.vector_score),
                        "final_score": float(row.final_score)
                    })
                    selected_ids.add(row.id)
            return results

    def add_council_minute(self, user_id: str, session_id: str, topic: str, participants: List[str], consensus: str, transcript: str, embedding: List[float]) -> str:
        """
        Logs a Council Session with vector embedding.
        """
        new_id = str(uuid.uuid4())
        with self.engine.begin() as conn:
            query = text("""
                INSERT INTO council_minutes (id, user_id, session_id, topic, participants, consensus, transcript, embedding, created_at)
                VALUES (:id, :uid, :sid, :topic, :parts, :consensus, :transcript, :emb, :ts)
            """)
            
            conn.execute(query, {
                "id": new_id,
                "uid": user_id,
                "sid": session_id,
                "topic": topic,
                "parts": ", ".join(participants),
                "consensus": consensus,
                "transcript": transcript,
                "emb": self._ensure_string_embedding(embedding),
                "ts": datetime.utcnow()
            })
            return new_id

    def search_similar_minutes(self, topic: str, user_id: Optional[str] = None, limit: int = 5) -> List[Dict]:
        """
        Retrieves past council minutes based on topic text similarity (PostgreSQL Full Text Search).

        2026-07-14: added `user_id` filtering. Previously this searched
        across every tenant's council_minutes with no isolation at all —
        the same class of cross-tenant leak fixed in AgentState
        (workspace/*/STATE.md had no user_id either).
        """
        if self.engine.dialect.name == "sqlite":
            return []

        with self.engine.connect() as conn:
            query_str = """
                SELECT id, topic, consensus, ts_rank(to_tsvector('simple', topic), plainto_tsquery('simple', :topic)) as rank
                FROM council_minutes
                WHERE to_tsvector('simple', topic) @@ plainto_tsquery('simple', :topic)
            """
            params = {"topic": topic, "limit": limit}
            if user_id is not None:
                query_str += " AND user_id = :uid"
                params["uid"] = user_id
            query_str += " ORDER BY rank DESC LIMIT :limit"

            rows = conn.execute(text(query_str), params).fetchall()

            return [{
                "id": row.id,
                "topic": row.topic,
                "consensus": row.consensus,
                "rank": row.rank
            } for row in rows]

    def search_similar_minutes_by_embedding(self, embedding: List[float], user_id: Optional[str] = None, limit: int = 5, threshold: float = 0.7) -> List[Dict]:
        """
        Retrieves past council minutes based on embedding similarity (PostgreSQL pgvector),
        re-ranked by a recency-weighted score = 0.7*cosine + 0.3*exp(-age_days/30).

        2026-07-14: raised default k from 1 to 5 (was starving the council
        of memory — only the single closest match ever surfaced) and added
        `user_id` filtering (previously searched across every tenant's
        council_minutes with no isolation at all).
        """
        if self.engine.dialect.name == "sqlite":
            return []

        with self.engine.connect() as conn:
            query_str = """
                SELECT id, topic, consensus, created_at,
                       1 - (embedding <=> :emb) as similarity,
                       (0.7 * (1 - (embedding <=> :emb)))
                       + (0.3 * EXP(-EXTRACT(EPOCH FROM (NOW() - created_at)) / 86400.0 / 30.0)) as score
                FROM council_minutes
                WHERE embedding IS NOT NULL AND 1 - (embedding <=> :emb) > :threshold
            """
            params = {
                "emb": self._ensure_string_embedding(embedding),
                "threshold": threshold,
                "limit": limit,
            }
            if user_id is not None:
                query_str += " AND user_id = :uid"
                params["uid"] = user_id
            query_str += " ORDER BY score DESC LIMIT :limit"

            rows = conn.execute(text(query_str), params).fetchall()

            return [{
                "id": row.id,
                "topic": row.topic,
                "consensus": row.consensus,
                "similarity": row.similarity,
                "score": row.score,
                "created_at": row.created_at,
            } for row in rows]

    def list_minutes(self, user_id: str, limit: int = 20) -> List[Dict]:
        """P5.2 (2026-07-11): recent council minutes for the debate-transparency view."""
        with self.engine.connect() as conn:
            rows = conn.execute(text("""
                SELECT id, session_id, topic, consensus, created_at
                FROM council_minutes
                WHERE user_id = :uid
                ORDER BY created_at DESC LIMIT :limit
            """), {"uid": user_id, "limit": limit}).fetchall()
            return [{
                "id": r.id, "session_id": r.session_id, "topic": r.topic,
                "consensus_preview": (r.consensus or "")[:200],
                "created_at": r.created_at,
            } for r in rows]

    def get_minute(self, minute_id: str) -> Optional[Dict]:
        """P5.2 (2026-07-11): full council minute (topic/consensus/transcript) by id."""
        with self.engine.connect() as conn:
            row = conn.execute(text("""
                SELECT id, session_id, user_id, topic, participants, consensus, transcript, created_at
                FROM council_minutes WHERE id = :id
            """), {"id": minute_id}).fetchone()
            if not row:
                return None
            return {
                "id": row.id, "session_id": row.session_id, "user_id": row.user_id,
                "topic": row.topic, "participants": row.participants,
                "consensus": row.consensus, "transcript": row.transcript,
                "created_at": row.created_at,
            }
