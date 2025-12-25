import uuid
import uuid
from datetime import datetime
from sqlalchemy import text
from src.data.database import get_db_connection
import json

class FeedbackStore:
    def __init__(self, db_path=None):
        self.db_path = db_path

    def save_example(self, agent_name: str, context_embedding: list, response_text: str, outcome_score: float):
        """
        Save a feedback example with vector embedding.
        
        Args:
            agent_name: Name of the agent.
            context_embedding: List of floats representing the vector.
            response_text: The actual response content.
            outcome_score: Evaluation score (e.g., -1.0 to 1.0).
        """
        conn = get_db_connection(self.db_path)
        try:
            query = text("""
                INSERT INTO agent_feedback (id, agent_name, context_embedding, response_text, outcome_score, timestamp)
                VALUES (:id, :agent_name, :embedding, :response, :score, :timestamp)
            """)
            
            conn.execute(query, {
                "id": str(uuid.uuid4()),
                "agent_name": agent_name,
                "embedding": str(context_embedding), # pgvector expects string representation like '[0.1, 0.2, ...]' or use adapter
                "response": response_text,
                "score": outcome_score,
                "timestamp": datetime.now().isoformat()
            })
            conn.commit()
        except Exception as e:
            # Check if it's a "no such table" error (sqlite fallback)
            # or vector type error
            print(f"FeedbackStore Save Error: {e}")
            raise e
        finally:
            conn.close()

    def get_similar_examples(self, agent_name: str, query_embedding: list, k=5):
        """
        Retrieve k most similar examples using cosine similarity (<=>).
        Requires pgvector extension.
        """
        conn = get_db_connection(self.db_path)
        try:
            # Using L2 distance (<->) or Cosine distance (<=>)
            # Start with L2 <-> for simplicity as per pgvector docs often default
            # But for embeddings cosine is usually better: <=> 
            query = text("""
                SELECT response_text, outcome_score, 1 - (context_embedding <=> :embedding) as similarity
                FROM agent_feedback
                WHERE agent_name = :agent_name
                ORDER BY context_embedding <=> :embedding
                LIMIT :k
            """)
            
            result = conn.execute(query, {
                "agent_name": agent_name,
                "embedding": str(query_embedding),
                "k": k
            }).fetchall()
            
            return [
                {"response": row[0], "score": row[1], "similarity": row[2]}
                for row in result
            ]
        except Exception as e:
            print(f"FeedbackStore Fetch Error: {e}")
            return []
        finally:
            conn.close()
