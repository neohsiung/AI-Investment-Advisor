from src.utils.logger import setup_logger
logger = setup_logger("VectorRepository")

import uuid
import json
from abc import ABC, abstractmethod
import typing
from typing import List, Dict, Tuple, Any, Optional, Callable, Dict, List, Tuple, Any, Optional, Callable
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
    def search_similar_minutes_by_embedding(self, embedding: List[float], limit: int = 1, threshold: float = 0.7) -> List[Dict]:
        """
        Retrieves past council minutes based on embedding similarity.
        根據嵌入相似度檢索過去的議會記錄。
        """
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
            # v4.2.1: Aligned with database.py (created_at instead of timestamp)
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
        QMD Architecture (Phase 2): 0.7 Vector + 0.3 BM25 + Temporal Decay + MMR Re-ranking.
        """
        if self.engine.dialect.name == "sqlite":
            logger.warning("Vector search skipped on SQLite.")
            return []

        with self.engine.connect() as conn:
            # PostgreSQL pgvector + Full Text Search + Temporal Decay
            # 1. Vector similarity (Cosine: 1 - distance) -> Using <-> L2 distance or <=> Cosine. We use <=> for cosine.
            # 2. BM25 (ts_rank with plainto_tsquery). If query_text is empty, BM25 score is 0.
            # 3. Temporal Decay: e^(-days_ago / 30). Halves roughly every 21 days.
            
            # Note: We fetch more than top_k for MMR re-ranking in python later if needed,
            # but for now we apply the combined score directly in DB for efficiency.
            
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
                    -- Temporal Decay: e^(-days / 30)
                    exp(-1 * EXTRACT(EPOCH FROM (NOW() - v.created_at)) / (86400 * 30)) as decay_factor,
                    v.vector_score,
                    COALESCE(t.text_score / m.max_score, 0) as norm_text_score,
                    -- Final Score: (0.7 * Vector + 0.3 * BM25) * Decay
                    (0.7 * v.vector_score + 0.3 * COALESCE(t.text_score / m.max_score, 0)) * 
                    exp(-1 * EXTRACT(EPOCH FROM (NOW() - v.created_at)) / (86400 * 30)) as final_score
                FROM vector_scores v
                JOIN text_scores t ON v.id = t.id
                CROSS JOIN max_text m
                WHERE v.vector_score > :threshold  -- Pre-filter by vector similarity
                ORDER BY final_score DESC
                LIMIT :limit
            """
            
            query = text(sql)
            
            rows = conn.execute(query, {
                "uid": user_id,
                "emb": self._ensure_string_embedding(embedding),
                "qtext": query_text,
                "threshold": threshold,
                "limit": top_k * 2 # Fetch double for potential MMR filtering later
            }).fetchall()

            # --- MMR (Maximal Marginal Relevance) Re-ranking (Simulated) ---
            # Basic implementation: Filter out results that are too similar to already selected ones.
            # For a pure DB approach, we just take the top_k of the combined score.
            # To do real MMR, we would need to compare embeddings of results against each other,
            # which is easier in python but requires fetching embeddings. 
            # We will approximate by just returning the highest weighted scores for now as Phase 2 start.
            
            results = []
            selected_ids = set()
            
            for row in rows:
                if len(results) >= top_k:
                    break
                    
                # Simple exact content deduplication
                if row.id not in selected_ids:
                    results.append({
                        "id": row.id,
                        "content": row.content,
                        "metadata": json.loads(row.metadata) if row.metadata else {},
                        "similarity": float(row.vector_score), # Keep original vector sim for reference
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
            # v4.2.1: Aligned with database.py schema (including user_id and consensus)
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

    def search_similar_minutes_by_embedding(self, embedding: List[float], limit: int = 1, threshold: float = 0.7) -> List[Dict]:
        """
        Retrieves past council minutes based on embedding similarity (PostgreSQL pgvector).
        """
        if self.engine.dialect.name == "sqlite":
            return []

        with self.engine.connect() as conn:
            query = text("""
                SELECT id, consensus, 1 - (embedding <=> :emb) as similarity
                FROM council_minutes
                WHERE 1 - (embedding <=> :emb) > :threshold
                ORDER BY similarity DESC
                LIMIT :limit
            """)
            
            rows = conn.execute(query, {
                "emb": self._ensure_string_embedding(embedding),
                "threshold": threshold,
                "limit": limit
            }).fetchall()
            
            return [{
                "id": row.id,
                "consensus": row.consensus,
                "similarity": row.similarity
            } for row in rows]
