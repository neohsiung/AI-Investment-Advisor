from datetime import datetime
import uuid
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
from sqlalchemy import text
from src.data.database import BaseRepository, get_db_engine, get_db_connection

class IFeedbackRepository(ABC):
    """
    Interface for Feedback Repository.
    回饋儲存庫介面。
    """
    @abstractmethod
    def add_review(self, reviewer: str, reviewee: str, score: int, comment: str, context_hash: str = None) -> str:
        """
        Add a peer review (HR 360).
        新增同儕審查 (HR 360)。
        """
        pass

    @abstractmethod
    def get_reviews_for_agent(self, agent_name: str) -> List[Dict[str, Any]]:
        """
        Get reviews RECEIVED by an agent.
        取得代理人收到的回饋。
        """
        pass

    @abstractmethod
    def get_reviews_by_agent(self, agent_name: str) -> List[Dict[str, Any]]:
        """
        Get reviews GIVEN by an agent.
        取得代理人給出的回饋。
        """
        pass

class AlchemyFeedbackRepository(BaseRepository, IFeedbackRepository):
    """
    Implementation of IFeedbackRepository using SQLAlchemy.
    使用 SQLAlchemy 實作的 IFeedbackRepository。
    """
    def __init__(self, engine: Any = None):
        """
        Initialize the repository.
        初始化儲存庫。
        """
        BaseRepository.__init__(self, engine or get_db_engine())

    def add_review(self, reviewer: str, reviewee: str, score: int, comment: str, context_hash: str = None) -> str:
        """
        Add a peer review (HR 360).
        新增同儕審查 (HR 360)。
        """
        with self.engine.begin() as conn:
            review_id = str(uuid.uuid4())
            timestamp = datetime.now().isoformat()
            
            stmt = text("""
                INSERT INTO agent_reviews (id, reviewer, reviewee, score, comment, context_hash, timestamp)
                VALUES (:id, :reviewer, :reviewee, :score, :comment, :context_hash, :timestamp)
            """)
            
            conn.execute(stmt, {
                "id": review_id,
                "reviewer": reviewer,
                "reviewee": reviewee,
                "score": score,
                "comment": comment,
                "context_hash": context_hash,
                "timestamp": timestamp
            })
            
            return review_id

    def get_reviews_for_agent(self, agent_name: str) -> List[Dict[str, Any]]:
        """
        Get reviews RECEIVED by an agent.
        取得代理人收到的回饋。
        """
        with self.engine.connect() as conn:
            stmt = text("SELECT * FROM agent_reviews WHERE reviewee = :agent_name ORDER BY timestamp DESC")
            result = conn.execute(stmt, {"agent_name": agent_name})
            return [dict(row._mapping) for row in result]

    def get_reviews_by_agent(self, agent_name: str) -> List[Dict[str, Any]]:
        """
        Get reviews GIVEN by an agent.
        取得代理人給出的回饋。
        """
        with self.engine.connect() as conn:
            stmt = text("SELECT * FROM agent_reviews WHERE reviewer = :agent_name ORDER BY timestamp DESC")
            result = conn.execute(stmt, {"agent_name": agent_name})
            return [dict(row._mapping) for row in result]

# Legacy alias removed in v4.1.7
# @deprecated: Use AlchemyFeedbackRepository
