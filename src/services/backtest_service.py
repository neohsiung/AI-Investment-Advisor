import yfinance as yf
import pandas as pd
import json
import logging
from datetime import timedelta, datetime
from typing import Optional, Any

from src.agents.factory import AgentFactory
from src.services.evaluation_service import EvaluationService

# Domain & Infrastructure
from src.domain.entities import SecurityContext, FeedbackExample, SignalType
from src.repositories.feedback_repository import AlchemyFeedbackRepository

logger = logging.getLogger("BacktestService")

class BacktestService:
    """
    Service for simulating historical market environments and evaluating agent decisions.
    回測服務：負責模擬過去的市場環境，執行 Agent 的決策邏輯，並產生回饋數據。
    
    Attributes:
        feedback_repo (IFeedbackRepository): Repository for storing feedback data.
        feedback_repo (IFeedbackRepository): 負責儲存回饋數據的儲存庫。
    """

    def __init__(self, feedback_repo: Optional[Any] = None):
        """
        Initialize the backtest service.
        初始化回測服務。
        """
        # Dependency Injection: Allow injecting Repository, default to Alchemy (Postgres) implementation
        # 相依注入：允許注入 Repository，預設使用 SQLAlchemy (Postgres) 實作
        from src.repositories.feedback_repository import AlchemyFeedbackRepository
        self.feedback_repo = feedback_repo if feedback_repo else AlchemyFeedbackRepository()

    def run_simulation(self, ticker: str, days_back: int = 30) -> None:
        """
        Execute a day-by-day simulation for a specific ticker.
        針對特定標的執行逐日模擬。
        
        Args:
            ticker (str): The stock symbol (e.g., 'AAPL').
            ticker (str): 股票代碼（例如 'AAPL'）。
            days_back (int): Number of days to look back for simulation.
            days_back (int): 模擬回溯的天數。
        """
        print(f"--- Starting Backtest for {ticker} (Last {days_back} days) ---")
        
        # 1. 獲取歷史數據 (Fetch Historical Data)
        start_date = datetime.now() - timedelta(days=days_back + 60)
        # Avoid FutureWarning by explicit auto_adjust
        df = yf.download(ticker, start=start_date, progress=False, auto_adjust=False)
        
        if len(df) < 50:
            logger.warning(f"Not enough data for {ticker}")
            return

        # 2. 初始化 Agent (Initialize Agent)
        # 使用 Factory 模式建立 Momentum Agent
        agent = AgentFactory.create_agent("Momentum", None) 
        
        count = 0
        market_days = df.index
        # Find the index corresponding to 'days_back' ago
        sim_start_idx = len(market_days) - days_back - 5 
        
        if sim_start_idx < 50: 
            sim_start_idx = 50 # Ensure enough warm-up data

        # 3. 逐日模擬 (Day-by-Day Simulation)
        for i in range(sim_start_idx, len(market_days) - 5):
            try:
                current_date = market_days[i]
                current_date_idx = i
                
                # 4. 建構 Context (Simulated Market View)
                history_slice = df.iloc[:current_date_idx+1]
                
                # Check if 'Close' is MultiIndex or single
                close_col = history_slice['Close']
                if isinstance(close_col, pd.DataFrame):
                     close_prices = close_col.iloc[:, 0].tolist() 
                else:
                     close_prices = close_col.tolist()
                
                context = {
                    "ticker": ticker,
                    "prices": close_prices[-20:], 
                    "indicators": {
                        "RSI": 50, # Placeholder
                        "MACD": "Bullish" # Placeholder
                    }
                }
                
                # Domain Entity
                sec_context = SecurityContext(
                    ticker=ticker,
                    date=current_date,
                    price=close_prices[-1],
                    indicators=context['indicators']
                )
                
                # 5. 執行 Agent (Execute Agent)
                response = agent.run(context)
                
                # 6. 評估結果 (Evaluate Outcome)
                future_val = df.iloc[current_date_idx + 5]['Close']
                current_val = df.iloc[current_date_idx]['Close']
                
                if isinstance(future_val, pd.Series): future_val = future_val.iloc[0]
                if isinstance(current_val, pd.Series): current_val = current_val.iloc[0]
                
                future_price = float(future_val)
                current_price = float(current_val)
                
                # Extract Signal from Response
                signal_str = "HOLD"
                resp_str = str(response).upper()
                if "BUY" in resp_str:
                    signal_str = "BUY"
                elif "SELL" in resp_str:
                    signal_str = "SELL"
                
                # Calculate Score
                score = EvaluationService.calculate_score(signal_str, current_price, future_price)
                
                # 7. 儲存回饋 (Store Feedback)
                example = FeedbackExample(
                    id=None,
                    agent_name="Momentum",
                    context=sec_context,
                    response_text=str(response),
                    signal=SignalType(signal_str),
                    outcome_score=score,
                    timestamp=datetime.now()
                )
                
                self.feedback_repo.save(example)

                print(f"  [Sim] Date: {current_date.date()} | Signal: {signal_str} | Return: {(future_price/current_price -1):.1%} | Score: {score}")
                count += 1
                
            except Exception as e:
                logger.error(f"Error in backtest loop: {e}")
                
        print(f"--- Backtest Complete. Generated {count} feedback examples. ---")

if __name__ == "__main__":
    BacktestService().run_simulation("AAPL", days_back=10)
