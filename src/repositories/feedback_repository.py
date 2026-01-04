from datetime import datetime
import uuid
from sqlalchemy import text
from src.data.database import get_db_connection

class SqliteFeedbackRepository:
    def __init__(self, connection=None):
        self._connection = connection

    def get_connection(self):
        if self._connection:
            return self._connection
        return get_db_connection()

    def add_review(self, reviewer: str, reviewee: str, score: int, comment: str, context_hash: str = None):
        """
        Add a peer review (HR 360).
        """
        conn = self.get_connection()
        try:
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
            
            if not self._connection:
                conn.commit()
            
            return review_id
        except Exception as e:
            if not self._connection:
                conn.rollback()
            raise e
        finally:
            if not self._connection:
                conn.close()

    def get_reviews_for_agent(self, agent_name: str):
        """Get reviews RECEIVED by an agent."""
        conn = self.get_connection()
        try:
            stmt = text("SELECT * FROM agent_reviews WHERE reviewee = :agent_name ORDER BY timestamp DESC")
            result = conn.execute(stmt, {"agent_name": agent_name})
            return [dict(row._mapping) for row in result]
        finally:
            if not self._connection:
                conn.close()

    def get_reviews_by_agent(self, agent_name: str):
        """Get reviews GIVEN by an agent."""
        conn = self.get_connection()
        try:
            stmt = text("SELECT * FROM agent_reviews WHERE reviewer = :agent_name ORDER BY timestamp DESC")
            result = conn.execute(stmt, {"agent_name": agent_name})
            return [dict(row._mapping) for row in result]
        finally:
            if not self._connection:
                 conn.close()
