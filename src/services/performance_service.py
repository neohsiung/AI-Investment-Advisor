import pandas as pd
from sqlalchemy import text
from src.data.database import get_db_connection
from src.utils.time_utils import get_current_time

class PerformanceService:
    def __init__(self, db_path=None):
        self.db_path = db_path # Uses default if None

    def record_recommendation(self, agent_name, ticker, signal, price, outcome_score=0):
        """Log a new recommendation signal."""
        import uuid
        conn = None
        try:
            conn = get_db_connection(self.db_path)
            rec_id = str(uuid.uuid4())
            date_str = get_current_time().isoformat()
            conn.execute(text("""
                INSERT INTO recommendations (id, date, agent, ticker, signal, price_at_signal, outcome_score)
                VALUES (:id, :date, :agent, :ticker, :signal, :price, :score)
            """), {
                "id": rec_id,
                "date": date_str,
                "agent": agent_name,
                "ticker": ticker,
                "signal": signal,
                "price": price,
                "score": outcome_score
            })
            conn.commit()
        except Exception as e:
            print(f"Failed to record recommendation: {e}")
        finally:
            if conn:
                conn.close()

    def get_agent_performance(self):
        """
        Calculate Win Rate for each agent.
        Returns dict: {'Momentum': {'win_rate': 0.6, 'count': 10}, ...}
        
        Note: Outcome score needs to be updated by a separate process that checks price history later.
        For now, we just return the raw stats of what we have.
        """
        conn = None
        try:
            conn = get_db_connection(self.db_path)
            # Assumes outcome_score is updated to 1 (win) or -1 (loss) by a backchecker
            query = text("""
                SELECT agent, COUNT(*) as total, SUM(CASE WHEN outcome_score > 0 THEN 1 ELSE 0 END) as wins
                FROM recommendations
                GROUP BY agent
            """)
            df = pd.read_sql(query, conn)
            
            stats = {}
            for _, row in df.iterrows():
                total = row['total']
                wins = row['wins']
                stats[row['agent']] = {
                    "win_rate": wins / total if total > 0 else 0,
                    "count": total
                }
            return stats
        except Exception as e:
            print(f"Error fetching agent performance: {e}")
            return {}
        finally:
            if conn:
                conn.close()

    def calculate_portfolio_alpha(self, portfolio_return, market_return):
        """Simple Alpha calculation."""
        return portfolio_return - market_return
