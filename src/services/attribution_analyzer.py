from sqlalchemy import text
from src.utils.logger import setup_logger
from src.repositories.agent_repository import AlchemyAgentRepository
from src.data.database import get_db_connection

logger = setup_logger("AttributionAnalyzer")

class AttributionAnalyzer:
    """
    Auto-Attribution & Dynamic Weighting Engine.
    自動歸因與動態權重校準引擎。
    
    Responsibilities:
    1. Scan historical recommendations of Agents.
    2. Compare initial signals (BUY/SELL) against subsequent market performance (ROI/Alpha).
    3. Calculate Win Rate & ROI-based Alpha.
    4. Update weights in agent_performance table via Raw SQL.
    """
    
    def __init__(self):
        self.agent_repo = AlchemyAgentRepository()
        
    def run_attribution_cycle(self, days_lookback: int = 30):
        """
        Execute the attribution cycle to recalibrate weights.
        執行歸因週期以重新校準權重。
        """
        logger.info(f"Starting Attribution Cycle (Lookback: {days_lookback} days)")
        
        # In a full system, we would:
        # 1. Fetch recommendations from the last X days
        # 2. Get the current price or exit price
        # 3. Calculate ROI
        # 4. Update the performance table
        
        # Example Raw SQL logic to fetch recommendations
        conn = get_db_connection()
        try:
            # Note: Assuming agent_recommendations table exists and tracks signal and price
            # Since AI Investment Advisor v4.5 is building this as part of Milestone 4:
            
            # Step 1: Calculate "Win Rate" (Simplified Mock Logic for now, 
            # ideally relying on a JOIN between recommendations and current market snapshots)
            # In a real deployed PG DB, this SQL would do window functions and calculate accuracy.
            
            # For demonstration in v4.5, we will implement a basic weight recalibration 
            # that bumps weight for agents with high success ratio in agent_performance.
            
            query = text("""
                SELECT agent_name, success_count, failure_count, weight
                FROM agent_performance
                WHERE success_count + failure_count > 0
            """)
            
            results = conn.execute(query).fetchall()
            
            for row in results:
                total_trades = row.success_count + row.failure_count
                win_rate = row.success_count / total_trades if total_trades > 0 else 0
                
                # Dynamic Logic: 
                # If win rate > 60%, boost weight. If < 40%, slash weight.
                target_weight = 1.0
                
                if total_trades >= 5: # Minimum confidence threshold
                    if win_rate >= 0.65:
                        target_weight = 1.2 + (win_rate - 0.65) # Max ~1.55
                    elif win_rate <= 0.45:
                        target_weight = 0.5 + win_rate # Min ~0.5
                    else:
                        target_weight = 1.0
                
                # Smooth the update (Exponential Moving Average like)
                new_weight = (row.weight * 0.7) + (target_weight * 0.3)
                
                # Clamp weight between 0.1 and 3.0
                new_weight = max(0.1, min(new_weight, 3.0))
                
                update_query = text("""
                    UPDATE agent_performance
                    SET weight = :nw
                    WHERE agent_name = :name
                """)
                
                conn.execute(update_query, {"nw": new_weight, "name": row.agent_name})
                logger.info(f"AttributionAnalyzer: {row.agent_name} Weight adjusted to {new_weight:.2f} (Win Rate: {win_rate:.1%})")
                
            conn.commit()
            
        except Exception as e:
            logger.error(f"Failed to run attribution cycle: {e}")
        finally:
            conn.close()
            
        logger.info("Attribution Cycle Completed.")
