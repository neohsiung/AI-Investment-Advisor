import json
import logging
from typing import Dict, Any

from src.agents.base_agent import BaseAgent
from src.agents.swarm.role_swarm import RoleSwarm

logger = logging.getLogger(__name__)

class SentimentSubAgent(BaseAgent):
    """
    Generic Sub-Agent for Sentiment Swarm.
    Overrides `run()` to inject specific instructions while maintaining JSON output requirements if needed.
    """
    def __init__(self, name: str, instruction: str, tier: str, **kwargs):
        super().__init__(name=name, prompt_path="prompts/common/default_system.j2", tier=tier, **kwargs)
        self.instruction = instruction

    def run(self, context: Any) -> str:
        ctx_dump = json.dumps(context, indent=2, ensure_ascii=False) if isinstance(context, dict) else str(context)
        prompt_data = {
            "user_request": f"{self.instruction}\n\nData Context:\n{ctx_dump}"
        }
        return self.run_tool_loop(context=prompt_data)

class SentimentSwarm(RoleSwarm):
    """
    Sentiment Swarm replaces the old monolithic SentimentAgent.
    Distributes processing across 2 sub-agents to parallelize news scanning and social sentiment pulse.
    """
    def __init__(self, use_cache=True, ttl_hours=4, **kwargs):
        # Default 4 hours for Sentiment (News changes fast)
        user_id = kwargs.get("user_id", "system")
        super().__init__(name="SentimentSwarm", use_cache=use_cache, ttl_hours=ttl_hours, user_id=user_id, **kwargs)
        
        # Initialize Sub-Agents
        self.news_scanner = SentimentSubAgent(
            name="NewsScanner", 
            instruction="分析新聞標題與內容的情緒 (Analyze sentiment of news headlines and content). Provide a structured summary.",
            tier="fast",
            user_id=user_id,
            use_cache=use_cache,
            ttl_hours=ttl_hours
        )
        self.social_pulse = SentimentSubAgent(
            name="SocialPulse", 
            instruction="綜合評估市場情緒與社群動能 (Assess overall market pulse and momentum based on news and price action). Consider implied volatility or extreme sentiment behavior.",
            tier="adv",
            user_id=user_id,
            use_cache=use_cache,
            ttl_hours=ttl_hours
        )
        
        # Register to RoleSwarm
        self.register_agent("col_fast", self.news_scanner)
        self.register_agent("col_adv", self.social_pulse)
        
    def run(self, context: Any) -> str:
        """
        Takes same context as SentimentAgent:
        context: {
            "ticker": "AAPL",
            "news": ["Title - Source (Link)", ...],
            "price_change_percent": optional float
        }
        Returns JSON-string or summary string from swarm.
        """
        tickers = context.get("tickers", [])
        single_ticker = context.get("ticker", "UNKNOWN")
        
        if not tickers and single_ticker != "UNKNOWN":
            tickers = [single_ticker]
            
        market_data = context.get("market_data", {})
        reports = []
        
        for t in tickers:
            t_data = market_data.get(t, {}) if market_data else context
            news_list = t_data.get("news", [])
            
            if not news_list:
                reports.append(f"### {t} Sentiment Swarm Analysis\nNeutral (No News)")
                continue
                
            news_str = "\n".join([f"- {n.get('title', 'No Title')} ({n.get('source', 'Unknown')})" if isinstance(n, dict) else f"- {n}" for n in news_list[:10]])
            
            prompt_data = {
                "ticker": t,
                "news_list": news_str,
                "price_change_percent": t_data.get("price_change_percent", "N/A")
            }
            
            wrapped_ctx = {
                "user_request": f"Analyze overall sentiment for {t}.",
                "data": prompt_data
            }
            
            try:
                # Execution via Swarm Orchestrator
                res = super().run(wrapped_ctx)
                reports.append(f"### {t} Sentiment Swarm Analysis\n{res}")
            except Exception as e:
                logger.error(f"SentimentSwarm execution failed for {t}: {e}")
                reports.append(f"### {t} Analysis\nError: {e}")
                
        # To maintain compatibility with old SentimentAgent string-based JSON parsing in some places
        # The caller usually expects JSON, but RoleSwarm returns Markdown.
        # This will need to be handled by the caller or we can return the first ticker's sentiment as JSON if it's a single request.
        # However, for now, we return the concatenated reports.
        return "\n\n".join(reports)
