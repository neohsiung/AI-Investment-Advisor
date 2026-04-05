"""
Streaming Scheduler — Proactive Layer [Phase 17].
串流排程器 — 定期掃描關注清單，驅動主動式建議流程。
"""

import asyncio
import logging
from typing import List, Dict, Any
from src.data.database import get_db_engine
from src.repositories.usage_repository import UsageRepository
from src.services.market_data_service import MarketDataService
from src.agents.sensory_agent import SensoryAgent

logger = logging.getLogger(__name__)

class StreamingScheduler:
    """
    Background worker that performs proactive market scans for subscribers.
    """
    def __init__(self, interval_seconds: int = 900): # Default 15 mins
        self.interval = interval_seconds
        self._running = False
        self._market_data = MarketDataService()
        self._sensory = SensoryAgent()

    async def start(self):
        """Starts the proactive monitoring loop."""
        if self._running:
            return
        self._running = True
        logger.info(f"🚀 Proactive Streaming Scheduler started (Interval: {self.interval}s)")
        
        while self._running:
            try:
                await self._monitor_all_users()
            except Exception as e:
                logger.error(f"Error in sensory monitoring loop: {e}", exc_info=True)
            
            await asyncio.sleep(self.interval)

    def stop(self):
        """Stops the scheduler."""
        self._running = False
        logger.info("🛑 Proactive Streaming Scheduler stopped.")

    async def _monitor_all_users(self):
         """
         Fetches all Pro/Enterprise users and scans their watchlists.
         """
         # In a real SaaS, we query the DB for users with 'proactive_alerts' feature enabled.
         # For this implementation, we simulate scanning a generic set of interests.
         users_to_scan = [{"id": "system", "watchlist": ["TSLA", "NVDA", "AAPL"]}]
         
         for user in users_to_scan:
             user_id = user["id"]
             watchlist = user["watchlist"]
             
             logger.info(f"Scanning watchlist for user {user_id}: {watchlist}")
             
             tasks = [self._scan_ticker_for_alert(user_id, ticker) for ticker in watchlist]
             await asyncio.gather(*tasks)

    async def _scan_ticker_for_alert(self, user_id: str, ticker: str):
        """
        Retrieves market data and runs SensoryAgent to determine if an alert is needed.
        """
        try:
            # 1. Fetch Price/Context
            price_info = self._market_data.get_current_price(ticker)
            news = self._market_data.get_company_news(ticker, days=1)
            
            # 2. Run SensoryAgent (Small LLM)
            # We wrap the sync call_llm (from base_agent) in to_thread if needed,
            # but our sensory agent should be async-ready.
            res_str = await self._sensory.run({
                "ticker": ticker,
                "price_info": f"{price_info}",
                "recent_news": news
            })
            
            import json
            res = json.loads(res_str)
            
            if res.get("alert_needed"):
                reason = res.get("reason", "Unknown alert")
                urgency = res.get("urgency", "low")
                logger.info(f"🚨 ALERT for {user_id} on {ticker} ({urgency}): {reason}")
                
                # 3. Task 17.3: Push to Notification Service
                from src.services.notification_service import NotificationService
                notifier = NotificationService(user_id=user_id)
                await notifier.send_message(
                    message=f"🚨 *{ticker} 異動提醒 ({urgency})*\n\n{reason}\n\n是否需要進步一深度分析？",
                    channel="all"
                )
                
        except Exception as e:
            logger.error(f"Failed to scan {ticker} for user {user_id}: {e}")
