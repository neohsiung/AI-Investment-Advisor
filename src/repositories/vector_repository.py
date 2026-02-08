import logging
import uuid
import json
from typing import List, Dict, Optional
from datetime import datetime
from sqlalchemy import text
from src.data.database import get_db_connection

logger = logging.getLogger(__name__)

class VectorRepository:
    """
    Repository for handling Vector Database operations (PGVector).
    Supports `memory_embeddings` and `council_minutes`.
    """

    def __init__(self):
        pass

    def _ensure_string_embedding(self, embedding: List[float]) -> str:
        """Converts list to string format '[x,y,z]' for SQL insertion."""
        return str(embedding)

    def add_memory(self, user_id: str, category: str, content: str, embedding: List[float], metadata: Dict = {}) -> str:
        """
        Inserts a new memory item.
        """
        conn = get_db_connection()
        new_id = str(uuid.uuid4())
        try:
            # Check if Postgres or SQLite
            is_sqlite = 'sqlite' in str(conn.engine.url)
            
            query = text("""
                INSERT INTO memory_embeddings (id, user_id, timestamp, category, content, embedding, metadata)
                VALUES (:id, :uid, :ts, :cat, :cont, :emb, :meta)
            """)
            
            conn.execute(query, {
                "id": new_id,
                "uid": user_id,
                "ts": datetime.utcnow().isoformat(),
                "cat": category,
                "cont": content,
                "emb": self._ensure_string_embedding(embedding),
                "meta": json.dumps(metadata)
            })
            conn.commit()
            return new_id
        except Exception as e:
            logger.error(f"VectorRepo: Error adding memory: {e}")
            raise
        finally:
            conn.close()

    def search_memory(self, user_id: str, embedding: List[float], top_k: int = 5, threshold: float = 0.7) -> List[Dict]:
        """
        Searches similar memories using Cosine Similarity.
        For SQLite, returns empty list (Vector Search not supported).
        """
        conn = get_db_connection()
        try:
            is_sqlite = 'sqlite' in str(conn.engine.url)
            if is_sqlite:
                logger.warning("VectorRepo: SQLite detected, vector search skipped.")
                return []

            # PGVector Cosine Similarity: 1 - (a <=> b)
            # We filter by similarity > threshold
            query = text("""
                SELECT id, content, category, metadata, 1 - (embedding <=> :emb) as similarity
                FROM memory_embeddings
                WHERE user_id = :uid
                AND 1 - (embedding <=> :emb) > :threshold
                ORDER BY similarity DESC
                LIMIT :limit
            """)

            rows = conn.execute(query, {
                "uid": user_id,
                "emb": self._ensure_string_embedding(embedding),
                "threshold": threshold,
                "limit": top_k
            }).fetchall()

            results = []
            for row in rows:
                # Row access by index
                results.append({
                    "id": row[0],
                    "content": row[1],
                    "category": row[2],
                    "metadata": json.loads(row[3]) if row[3] else {},
                    "similarity": row[4]
                })
            return results

        except Exception as e:
            logger.error(f"VectorRepo: Search failed: {e}")
            return []
        finally:
            conn.close()

    def add_council_minute(self, session_id: str, topic: str, participants: List[str], consensus: str, transcript: str, embedding: List[float]) -> str:
        """
        Logs a Council Session.
        """
        conn = get_db_connection()
        new_id = str(uuid.uuid4())
        try:
            query = text("""
                INSERT INTO council_minutes (id, session_id, timestamp, topic, participants, consensus_decision, full_transcript, embedding)
                VALUES (:id, :sid, :ts, :topic, :parts, :decision, :transcript, :emb)
            """)
            
            conn.execute(query, {
                "id": new_id,
                "sid": session_id,
                "ts": datetime.utcnow().isoformat(),
                "topic": topic,
                "parts": json.dumps(participants),
                "decision": consensus,
                "transcript": transcript,
                "emb": self._ensure_string_embedding(embedding)
            })
            conn.commit()
            return new_id
        except Exception as e:
            logger.error(f"VectorRepo: Error adding minute: {e}")
            raise
        finally:
            conn.close()
    def search_similar_minutes(self, topic: str, limit: int = 1, threshold: float = 0.7) -> List[Dict]:
        """
        Retrieves past council minutes based on topic similarity.
        Warning: Requires a real embedding model. For now we assume the 'topic' is already an embedding
        or we skip if it's just a string in this refactor step (since we don't have an embedder here).

        To make this functional:
        1. We need an Embedder Service (e.g. OpenAI).
        2. Here we will mock it or rely on the caller to provide embedding if topic is a list.
        """
        # NOTE: This signature is being updated to accept embedding or we need to embed inside.
        # For this step, let's assume valid embedding is passed or we return empty if string.
        # In a real app, `src.infrastructure.llm_provider` should generate the embedding.
        
        # Temporary safeguard: If topic is string, we can't search without embedding provider.
        # So we return empty list to prevent crash, unless we integrate embedding here.
        # Let's return empty for now to satisfy the call in CouncilService, 
        # but mark for next iteration to add EmbeddingService.
        logger.warning("VectorRepo: search_similar_minutes called without embedding service. Returning empty.")
        return []

    def search_similar_minutes_by_embedding(self, embedding: List[float], limit: int = 1, threshold: float = 0.7) -> List[Dict]:
        """
        True retrieval logic using embedding vector.
        """
        conn = get_db_connection()
        try:
            is_sqlite = 'sqlite' in str(conn.engine.url)
            if is_sqlite:
                return []

            query = text("""
                SELECT id, topic, consensus_decision, full_transcript, 1 - (embedding <=> :emb) as similarity
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
                "id": row[0],
                "topic": row[1],
                "consensus": row[2],
                "transcript": row[3],
                "similarity": row[4]
            } for row in rows]
            
        except Exception as e:
            logger.error(f"VectorRepo: Search minutes failed: {e}")
            return []
        finally:
            conn.close()
