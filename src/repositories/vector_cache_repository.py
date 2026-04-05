"""
Vector Cache Repository — Data Layer [Phase 13].
語義快取儲存庫 — 負責快取 LLM Prompt 及其生成的回應。

Uses pgvector for cosine similarity search to enable semantic hits.
"""

import hashlib
import logging
from typing import List, Optional, Tuple, Any, Dict
from sqlalchemy import text
from src.data.database import BaseRepository, get_db_engine
from src.data.models import PromptCache

logger = logging.getLogger(__name__)

class VectorCacheRepository(BaseRepository):
    """
    Repository for Semantic Prompt Caching using pgvector.
    """
    def __init__(self, engine=None):
        super().__init__(engine or get_db_engine())

    def get_cached_response(self, user_id: str, prompt_text: str, embedding: List[float], threshold: float = 0.95) -> Optional[str]:
        """
        Find a semantically similar prompt in the cache.
        Returns: The cached response text or None.
        """
        # Exact match optimization (Hiding behind a hash for performance)
        p_hash = hashlib.sha256(prompt_text.encode()).hexdigest()
        
        try:
            # 1. First try exact match
            exact = self.session.query(PromptCache).filter_by(user_id=user_id, prompt_hash=p_hash).first()
            if exact:
                logger.info(f"💎 Cache Hit: Exact match for user {user_id}")
                return exact.response_text
            
            # 2. Semantic match using pgvector cosine distance
            # cosine_distance = 1 - cosine_similarity
            # Limit 1, distance < (1 - threshold)
            max_distance = 1.0 - threshold
            
            # Using raw SQL for pgvector operators as SQLAlchemy ORM might need extra config
            sql = text("""
                SELECT response_text, (embedding <=> :emb) as distance 
                FROM prompt_cache 
                WHERE user_id = :uid 
                AND (embedding <=> :emb) < :dist
                ORDER BY (embedding <=> :emb) ASC
                LIMIT 1
            """)
            
            res = self.session.execute(sql, {"emb": str(embedding), "uid": user_id, "dist": max_distance}).first()
            if res:
                logger.info(f"🧠 Cache Hit: Semantic match (dist={res.distance:.4f}) for user {user_id}")
                return res.response_text
                
            return None
        except Exception as e:
            logger.error(f"Cache lookup failed: {e}")
            return None
        finally:
            self.close_session()

    def save_cache(self, user_id: str, prompt_text: str, embedding: List[float], response_text: str, metadata: Dict[str, Any] = None):
        """
        Persist a prompt-response pair to the semantic cache.
        """
        p_hash = hashlib.sha256(prompt_text.encode()).hexdigest()
        
        try:
            cache_entry = PromptCache(
                user_id=user_id,
                prompt_hash=p_hash,
                prompt_text=prompt_text,
                embedding=embedding,
                response_text=response_text,
                metadata=metadata or {}
            )
            self.session.add(cache_entry)
            self.session.commit()
            logger.debug(f"💾 Cache Saved: Entry for user {user_id}")
        except Exception as e:
            self.session.rollback()
            logger.error(f"Failed to save cache entry: {e}")
        finally:
            self.close_session()
