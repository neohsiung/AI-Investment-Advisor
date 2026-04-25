import pandas as pd
import yfinance as yf
import typing
import os
import json
from typing import List, Dict, Tuple, Any, Optional, Callable, Dict, List, Tuple, Any, Optional, Callable
from datetime import datetime, timedelta
from src.utils.logger import setup_logger
from src.services.evaluation_service import EvaluationService
from src.domain.entities import SecurityContext, FeedbackExample, SignalType
from src.domain.interfaces import Message, LLMConfig
from src.infrastructure.llm.tier_config import SettingsAwareModelRouter
from src.infrastructure.llm.llm_gateway import OpenRouterGateway
from src.repositories.settings_repository import AlchemySettingsRepository

logger = setup_logger("BacktestService")

class BacktestService:
    """
    Service for simulating historical market environments and evaluating agent decisions.
    回測服務：負責模擬過去的市場環境，執行 Agent 的決策邏輯，並產生回饋數據。
    
    PAD Phase 2: Migrated to SettingsAwareModelRouter + OpenRouterGateway
    
    Attributes:
        feedback_repo (IFeedbackRepository): Repository for storing feedback data.
        feedback_repo (IFeedbackRepository): 負責儲存回饋數據的儲存庫。
    """

    def __init__(self, feedback_repo: Optional[Any] = None, user_id: str = None):
        """
        Initialize the backtest service.
        初始化回測服務。
        """
        # Dependency Injection: Allow injecting Repository, default to Alchemy (Postgres) implementation
        # 相依注入：允許注入 Repository，預設使用 SQLAlchemy (Postgres) 實作
        from src.repositories.feedback_repository import AlchemyFeedbackRepository
        self.feedback_repo = feedback_repo if feedback_repo else AlchemyFeedbackRepository()
        self.user_id = user_id or "system"
        
        # PAD Phase 2: Initialize router and gateway for LLM calls
        self.settings_repo = AlchemySettingsRepository()
        self.model_router = SettingsAwareModelRouter(self.settings_repo)
        self.gateway = OpenRouterGateway()

    
    async def _call_agent_llm(self, agent_name: str, context: Dict[str, Any], tier: str = "smart", 
                              temperature: float = 0.7, max_tokens: int = 2000) -> str:
        """
        PAD Phase 2: Replace AgentFactory.create_*_agent().run() with direct gateway calls.
        Generic method to call LLM for any agent role.
        """
        try:
            model = self.model_router.get_model(self.user_id, tier)
            if not model:
                raise ValueError(f"Failed to route model for tier={tier}")
            
            agent_prompts = {
                "Momentum": "You are a Momentum analyst. Analyze price trends and technical indicators. Based on the provided market context, provide a BUY, SELL, or HOLD signal.",
                "Fundamental": "You are a Fundamental analyst. Analyze financial statements and valuations. Based on the provided market context, provide a BUY, SELL, or HOLD signal.",
                "Risk": "You are a Risk manager. Assess portfolio risks and downsides. Based on the provided market context, provide a BUY, SELL, or HOLD signal.",
                "Sentiment": "You are a Sentiment analyst. Analyze market sentiment and investor psychology. Based on the provided market context, provide a BUY, SELL, or HOLD signal.",
                "Macro": "You are a Macro strategist. Assess macroeconomic trends and cyclical factors. Based on the provided market context, provide a BUY, SELL, or HOLD signal."
            }
            
            system_prompt = agent_prompts.get(agent_name, f"You are a {agent_name} analyst. Provide a BUY, SELL, or HOLD signal.")
            messages = [
                Message(role="system", content=system_prompt),
                Message(role="user", content=json.dumps(context))
            ]
            
            config = LLMConfig(
                provider=os.getenv("AI_PROVIDER", "OpenRouter"),
                model=model,
                temperature=temperature,
                max_tokens=max_tokens
            )
            logger.debug(f"Backtest: Calling {agent_name} agent via {model}")
            response = await self.gateway.chat(messages, config)
            
            if not isinstance(response, str):
                raise ValueError(f"Unexpected response type from gateway: {type(response)}")
            
            return response
        except Exception as e:
            logger.error(f"Backtest: {agent_name} agent failed: {e}")
            raise

    async def run_simulation(self, ticker: str, days_back: int = 30) -> None:
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

        # 2. 初始化 Agent Context (Initialize Agent Context)
        # PAD Phase 2: Replace AgentFactory.create_agent() with _call_agent_llm()
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
                # PAD Phase 2: Use _call_agent_llm instead of agent.run()
                response = await self._call_agent_llm("Momentum", context, tier="fast")
                
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
                score = EvaluationService().calculate_score(signal_str, current_price, future_price)
                
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
