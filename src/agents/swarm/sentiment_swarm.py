import json
import typing
from typing import List, Dict, Tuple, Any, Optional, Callable, Any
from src.utils.logger import setup_logger
from src.agents.base_agent import BaseAgent
from .role_swarm import RoleSwarm

logger = setup_logger("SentimentSwarm")

class SentimentSubAgent(BaseAgent):
    def __init__(self, name: str, instruction: str, tier: str, **kwargs):
        super().__init__(name=name, prompt_path="prompts/common/default_system.j2", tier=tier, **kwargs)
        self.instruction = instruction

    async def run(self, context: Any) -> str:
        ctx_dump = json.dumps(context, indent=2, ensure_ascii=False) if isinstance(context, dict) else str(context)
        prompt_data = {
            "user_request": f"{self.instruction}\n\nData Context:\n{ctx_dump}"
        }
        return await self.run_tool_loop(context=prompt_data)

class SentimentSwarm(RoleSwarm):
    def __init__(self, use_cache=True, ttl_hours=4, **kwargs):
        user_id = kwargs.pop("user_id", None)
        if not user_id:
            raise ValueError("SentimentSwarm: user_id is required.")
        super().__init__(name="SentimentSwarm", use_cache=use_cache, ttl_hours=ttl_hours, user_id=user_id, **kwargs)
        
        self.news_scanner = SentimentSubAgent(
            name="NewsScanner", 
            instruction="分析新聞情緒 (Analyze sentiment of news).",
            tier="fast",
            user_id=user_id,
            use_cache=use_cache,
            ttl_hours=ttl_hours
        )
        self.social_pulse = SentimentSubAgent(
            name="SocialPulse", 
            instruction="評估市場情緒 (Assess overall market pulse).",
            tier="adv",
            user_id=user_id,
            use_cache=use_cache,
            ttl_hours=ttl_hours
        )
        
        self.register_agent("col_fast", self.news_scanner)
        self.register_agent("col_adv", self.social_pulse)
        
    async def run(self, context: Any) -> str:
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
            
            prompt_data = {
                "ticker": t,
                "news_list": news_list,
                "price_change_percent": t_data.get("price_change_percent", "N/A")
            }
            wrapped_ctx = {
                "user_request": f"Analyze overall sentiment for {t}.",
                "data": prompt_data
            }
            try:
                res = await super().run(wrapped_ctx)
                reports.append(f"### {t} Sentiment Swarm Analysis\n{res}")
            except Exception as e:
                logger.error(f"SentimentSwarm failed for {t}: {e}")
                reports.append(f"### {t} Analysis\nError: {e}")
        return "\n\n".join(reports)
