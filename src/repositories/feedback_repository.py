from datetime import datetime
import uuid
import json
from abc import ABC, abstractmethod
import typing
from typing import List, Dict, Tuple, Any, Optional, Callable, Dict, List, Tuple, Any, Optional, Callable
from sqlalchemy import text
from src.data.database import BaseRepository, get_db_engine, get_db_connection
from src.domain.entities import FeedbackExample, SecurityContext, SignalType

class IFeedbackRepository(ABC):
    """
    Interface for Feedback Repository.
    回饋儲存庫介面。
    """
    @abstractmethod
    def save(self, example: FeedbackExample) -> None:
        """
        Save a feedback example (Experience Training).
        儲存回饋範例 (經驗訓練)。
        """
        pass

    @abstractmethod
    def get_training_examples(self, agent_name: str, min_score: float, limit: int) -> List[FeedbackExample]:
        """
        Get training examples for an agent.
        取得代理人的訓練範例。
        """
        pass

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
    def __init__(self, db_path: str = None, engine: Any = None):
        """
        Initialize the repository.
        初始化儲存庫。
        """
        BaseRepository.__init__(self, engine or get_db_engine(db_path))

    def save(self, example: FeedbackExample) -> None:
        """
        Save a feedback example (Experience Training).
        儲存回饋範例 (經驗訓練)。
        """
        with self.engine.begin() as conn:
            stmt = text("""
                INSERT INTO agent_feedback (id, agent_name, context_text, response_text, signal, outcome_score, timestamp)
                VALUES (:id, :agent_name, :context_text, :response_text, :signal, :outcome_score, :timestamp)
            """)
            
            conn.execute(stmt, {
                "id": str(uuid.uuid4()) if not example.id else example.id,
                "agent_name": example.agent_name,
                "context_text": example.context.to_json() if example.context else None,
                "response_text": example.response_text,
                "signal": example.signal.value if example.signal else None,
                "outcome_score": example.outcome_score,
                "timestamp": example.timestamp
            })

    def get_training_examples(self, agent_name: str, min_score: float, limit: int) -> List[FeedbackExample]:
        """
        Get training examples for an agent.
        取得代理人的訓練範例。
        """
        with self.engine.connect() as conn:
            stmt = text("""
                SELECT agent_name, context_text, response_text, signal, outcome_score, timestamp, id
                FROM agent_feedback 
                WHERE agent_name = :agent_name AND outcome_score >= :min_score
                ORDER BY timestamp DESC
                LIMIT :limit
            """)
            result = conn.execute(stmt, {"agent_name": agent_name, "min_score": min_score, "limit": limit})
            
            examples = []
            for row in result:
                ctx_data = json.loads(row.context_text) if row.context_text else {}
                ctx = SecurityContext(
                    ticker=ctx_data.get("ticker", "UNKNOWN"),
                    date=datetime.fromisoformat(ctx_data.get("date")) if ctx_data.get("date") else datetime.now(),
                    price=ctx_data.get("price", 0.0),
                    indicators=ctx_data.get("indicators", {})
                )
                
                examples.append(FeedbackExample(
                    id=row.id,
                    agent_name=row.agent_name,
                    context=ctx,
                    response_text=row.response_text,
                    signal=SignalType(row.signal) if row.signal else SignalType.HOLD,
                    outcome_score=float(row.outcome_score),
                    timestamp=datetime.fromisoformat(str(row.timestamp)) if isinstance(row.timestamp, str) else row.timestamp
                ))
            return examples

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
