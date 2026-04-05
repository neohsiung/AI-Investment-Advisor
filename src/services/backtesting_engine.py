"""
Backtesting Engine Service — Infrastructure & Domain Layer [Phase 12].
回測引擎服務 — 提供沙盒回測與「時間旅行」功能。

Allows the agent to simulate decisions as if it were a specific date in the past,
injecting mock market data and overriding the system clock.
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from src.data.database import get_db_engine
from src.repositories.transaction_repository import AlchemyTransactionRepository

logger = logging.getLogger(__name__)

class BacktestEngine:
    """
    Simulation engine for "What-If" and Historical Performance Analysis.
    """
    def __init__(self, user_id: str):
        self.user_id = user_id
        self.tx_repo = AlchemyTransactionRepository(get_db_engine())

    async def simulate_turn(self, mock_date_str: str, ticker: str = None) -> Dict[str, Any]:
        """
        Simulates one advisor turn at a specific historical point.
        """
        try:
            mock_date = datetime.strptime(mock_date_str, "%Y-%m-%d")
            logger.info(f"🚀 Sandbox: Simulating turn for User {self.user_id} at {mock_date_str}")
            
            # 1. Setup Mock Context
            # v12.3: We can use ContextAssembler to gather historical data if providers support it.
            # For now, we return metadata to be used by the caller to override 'current_date'.
            
            return {
                "sandbox_active": True,
                "simulation_date": mock_date_str,
                "target_ticker": ticker or "Portfolio",
                "status": "ready"
            }
        except Exception as e:
            logger.error(f"Sandbox Simulation failed: {e}")
            return {"status": "error", "message": str(e)}

    def get_market_regime_override(self, date: datetime) -> Optional[str]:
        """
        Returns a mock market regime for a specific historical date.
        (e.g., '2020-03-20' -> 'Extreme Fear / Pandemic Crash')
        """
        # [NEW Phase 12] Hardcoded critical markers for backtesting scenarios
        markers = {
            "2020-03-20": "Pandemic Crash - High Volatility",
            "2021-11-01": "Tech Top - Excess Liquidity",
            "2022-06-15": "Inflation Peak - Bear Market",
            "2023-10-30": "AI Boom Commencement"
        }
        
        date_key = date.strftime("%Y-%m-%d")
        return markers.get(date_key)
