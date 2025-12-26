import logging
import uuid
from datetime import datetime
from sqlalchemy import text
from src.data.database import get_db_connection
from src.market_data import MarketDataService
from src.data.repositories.feedback_repository import SqliteFeedbackRepository
from src.domain.entities import FeedbackExample, SecurityContext, SignalType

logger = logging.getLogger("RefinementEngine")

class RefinementEngine:
    def __init__(self, db_path=None):
        self.db_path = db_path
        self.market_data = MarketDataService(db_path)
        self.feedback_repo = SqliteFeedbackRepository(db_path)

    def run_attribution_analysis(self):
        """
        1. Fetch unscored recommendations from 'recommendations' table.
        2. Validate against actual market price (MarketDataService).
        3. Score outcome (-1 to 1).
        4. Update 'recommendations' table.
        5. Save to 'agent_feedback' for Optimizer training.
        """
        logger.info("Running Attribution Analysis...")
        conn = get_db_connection(self.db_path)
        
        try:
            # 1. Fetch unscored (outcome_score = 0) from last 30 days
            # We filter by outcome_score = 0.
            # Ideally verify date > 30 days ago to avoid stale checks, or check only older than 1 week so price has moved.
            # For this impl, we check everything unscored.
            query = text("""
                SELECT id, date, agent, ticker, signal, price_at_signal 
                FROM recommendations 
                WHERE outcome_score = 0
            """)
            # Accessing fields via dot notation requires mappings() or using tuple indices if standard cursor
            # standard sqlalchemy execute returns ResultProxy, iterable of Row (which supports attribute access in recent versions)
            recs = conn.execute(query).fetchall()
            
            if not recs:
                logger.info("No unscored recommendations found.")
                return

            # Collect Tickers for batch price fetch
            tickers = list(set([row.ticker for row in recs]))
            current_prices = self.market_data.get_current_prices(tickers)

            for rec in recs:
                rec_id = rec.id
                ticker = rec.ticker
                signal = rec.signal
                entry_price = rec.price_at_signal
                agent_name = rec.agent
                date_str = rec.date
                
                curr_price = current_prices.get(ticker)
                
                # If price not found or entry_price is 0/invalid, skip
                if not curr_price or not entry_price:
                    logger.warning(f"Skipping {ticker}: Price data unavailable or invalid entry.")
                    continue

                # Calculate Score 
                # Defined: >5% gain = 1 (Win), <-5% loss = -1 (Loss), else 0 (Neutral)
                # Adjust for SELL.
                score = 0.0
                pct_change = (curr_price - entry_price) / entry_price
                
                if signal == "BUY":
                    if pct_change > 0.05: score = 1.0
                    elif pct_change < -0.05: score = -1.0
                    else: score = 0.1 # Slight move
                elif signal == "SELL":
                    if pct_change < -0.05: score = 1.0 # Price dropped, good sell
                    elif pct_change > 0.05: score = -1.0
                    else: score = 0.1
                else: 
                    # HOLD - harder to score, assume neutral
                    score = 0.0

                # Update recommendations table
                conn.execute(text("UPDATE recommendations SET outcome_score = :score WHERE id = :id"), 
                             {"score": score, "id": rec_id})
                
                # Migrate/Save to FeedbackRepository for Prompt Optimization
                # We define a minimal Context since we might not have stored the original context_text in 'recommendations'.
                # In a full v3 system, 'recommendations' should link to 'agent_states' or 'agent_feedback' directly.
                # Here we reconstruct for compatibility.
                
                try:
                    date_obj = datetime.fromisoformat(date_str) if date_str else datetime.now()
                except ValueError:
                    date_obj = datetime.now()

                context = SecurityContext(
                    ticker=ticker,
                    date=date_obj,
                    price=entry_price,
                    indicators={}, 
                    news_headlines=[],
                    financials={}
                )
                
                # Ensure valid signal enum
                try:
                    sig_enum = SignalType(signal)
                except ValueError:
                    sig_enum = SignalType.HOLD

                feedback_ex = FeedbackExample(
                    id=None,
                    agent_name=agent_name,
                    context=context,
                    response_text=f"Signal: {signal} (Auto-Generated by Refinement)", 
                    signal=sig_enum,
                    outcome_score=score
                )
                
                self.feedback_repo.save(feedback_ex)
                logger.info(f"Scored {agent_name} on {ticker}: {score} (Current: {curr_price}, Entry: {entry_price})")

            conn.commit()
            logger.info("Attribution Analysis Completed.")

        except Exception as e:
            logger.error(f"Error in attribution analysis: {e}")
        finally:
            conn.close()

if __name__ == "__main__":
    from src.utils.logger import setup_logger
    setup_logger("RefinementEngine")
    engine = RefinementEngine()
    engine.run_attribution_analysis()
