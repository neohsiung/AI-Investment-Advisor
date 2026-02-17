import uuid
import uuid
from datetime import datetime
from sqlalchemy import text
from src.data.database import get_db_connection
import json

class FeedbackStore:
    def __init__(self, db_path=None):
        self.db_path = db_path

    def save_example(self, agent_name: str, context_embedding: list, response_text: str, outcome_score: float, context_text: str = None):
        """
        Save a feedback example with vector embedding.
        """
        conn = get_db_connection(self.db_path)
        try:
            query = text("""
                INSERT INTO agent_feedback (id, agent_name, context_embedding, context_text, response_text, outcome_score, timestamp)
                VALUES (:id, :agent_name, :embedding, :context_text, :response, :score, :timestamp)
            """)
            
            conn.execute(query, {
                "id": str(uuid.uuid4()),
                "agent_name": agent_name,
                "embedding": str(context_embedding) if context_embedding else None,
                "context_text": context_text,
                "response": response_text,
                "score": outcome_score,
                "timestamp": datetime.now()
            })
            conn.commit()
        except Exception as e:
            logger.error(f"FeedbackStore Save Error: {e}")
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
                SELECT response_text, outcome_score, 1 - (context_embedding <=> :embedding) as similarity, context_text
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
                {"response": row[0], "score": row[1], "similarity": row[2], "context": row[3]}
                for row in result
            ]
        except Exception as e:
            print(f"FeedbackStore Fetch Error: {e}")
            return []
        finally:
            conn.close()

    def get_examples_for_training(self, agent_name: str, min_score: float = 0.5, limit: int = 50):
        """
        Fetch examples with score >= min_score for training.
        Returns a list of dicts: {"context": ..., "response": ...}
        """
        conn = get_db_connection(self.db_path)
        try:
            query = text("""
                SELECT context_text, response_text, outcome_score
                FROM agent_feedback
                WHERE agent_name = :agent_name AND outcome_score >= :min_score
                ORDER BY timestamp DESC
                LIMIT :limit
            """)
            
            rows = conn.execute(query, {
                "agent_name": agent_name,
                "min_score": min_score,
                "limit": limit
            }).fetchall()
            
            examples = []
            for row in rows:
                if row[0]: # Ensure context exists
                    examples.append({
                        "context": row[0], # Keep as string (JSON) or parse? DSPy might expect string if signature is string.
                        "response": row[1],
                        "score": row[2]
                    })
            return examples
        except Exception as e:
            print(f"Error fetching training examples: {e}")
            return []
        finally:
            conn.close()
