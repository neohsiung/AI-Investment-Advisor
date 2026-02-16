import json
import logging
import asyncio
from typing import Any, List, Dict
from src.agents.swarm.role_swarm import RoleSwarm
from src.agents.base_agent import BaseAgent

logger = logging.getLogger(__name__)

class SentimentScanner(BaseAgent):
    """
    Fast Tier Agent for Sentiment Scanning.
    Analyzes news headlines/snippets for a single ticker.
    """
    def __init__(self, user_id="system", **kwargs):
        kwargs.pop('tier', None)
        super().__init__(
            name="SentimentScanner", 
            prompt_path="prompts/sentiment_agent.txt", 
            tier="fast", 
            user_id=user_id, 
            **kwargs
        )
        
    def run(self, context):
        """
        Expects context with 'ticker' and 'news_str' or 'news_list'.
        Returns JSON string or dict.
        """
        return self.run_tool_loop(context)

class SentimentSwarm(RoleSwarm):
    """
    Sentiment Analysis Swarm.
    Parallel processing of market sentiment using Fast Tier agents.
    """
    def __init__(self, user_id: str = "system", **kwargs):
        super().__init__(name="SentimentSwarm", user_id=user_id, **kwargs)
        
        # Register default pool
        for _ in range(3):
            self.register_agent("col_fast", SentimentScanner(user_id=user_id))
            
    async def _run_async(self, context: Any) -> str:
        """
        Batch process sentiment for multiple tickers.
        """
        tickers = context.get("tickers", [])
        ticker = context.get("ticker")
        
        if ticker and ticker != "UNKNOWN":
            tickers = [ticker]
            
        if not tickers:
            return "No tickers provided for Sentiment Analysis."
            
        market_data = context.get("market_data", {})
        
        # Dynamic creation of scanners for coverage
        adhoc_agents = []
        tasks_list = []
        contexts_list = []
        
        for t in tickers:
            agent = SentimentScanner(user_id=self.user_id)
            agent.name = f"Sentiment_{t}" # Unique name for logging
            adhoc_agents.append(agent)
            
            # Prepare context
            t_data = market_data.get(t, {})
            news = t_data.get("news", [])
            price_change = t_data.get("price_change_percent", "N/A")
            
            # Format news for the prompt
            news_str = "\n".join([f"- {n.get('title', 'No Title')} ({n.get('source', 'Unknown')})" for n in news[:5]])
            if not news_str:
                news_str = "No recent news found."
                
            sub_context = {
                "ticker": t,
                "news_list": news_str,
                "price_change_percent": price_change,
                "user_request": f"Analyze sentiment for {t}"
            }
            
            tasks_list.append(sub_context["user_request"])
            contexts_list.append(sub_context)
            
        logger.info(f"SentimentSwarm: ⚡ Scanning {len(tickers)} tickers...")
        
        # Batch Run
        results_dict = await self.orchestrator.batch_run(adhoc_agents, tasks_list, contexts_list)
        
        # Aggregate
        # We might want to parse JSONs here and aggregate scores, 
        # but for now we basically concatenate reports.
        summary = self.orchestrator.aggregate_results(results_dict)
        
        return summary
