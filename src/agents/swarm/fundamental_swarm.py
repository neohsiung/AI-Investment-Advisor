import json
import typing
from typing import List, Dict, Tuple, Any, Optional, Callable, Any
from src.utils.logger import setup_logger
from src.agents.base_agent import BaseAgent
from .role_swarm import RoleSwarm
from src.services.supply_chain_service import SupplyChainService

logger = setup_logger("FundamentalSwarm")

class FundamentalSubAgent(BaseAgent):
    def __init__(self, name: str, instruction: str, tier: str, **kwargs):
        super().__init__(name=name, prompt_path="prompts/common/default_system.j2", tier=tier, **kwargs)
        self.instruction = instruction

    async def run(self, context: Any) -> str:
        ctx_dump = json.dumps(context, indent=2, ensure_ascii=False) if isinstance(context, dict) else str(context)
        prompt_data = {
            "user_request": f"{self.instruction}\n\nData Context:\n{ctx_dump}"
        }
        return await self.run_tool_loop(context=prompt_data)

class FundamentalSwarm(RoleSwarm):
    def __init__(self, use_cache=True, ttl_hours=None, **kwargs):
        ttl = ttl_hours if ttl_hours is not None else 24
        user_id = kwargs.pop("user_id", None)
        if not user_id:
            raise ValueError("FundamentalSwarm: user_id is required.")
        super().__init__(name="FundamentalSwarm", use_cache=use_cache, ttl_hours=ttl, user_id=user_id, **kwargs)
        
        self.revenue_extractor = FundamentalSubAgent(
            name="RevenueExtractor", 
            instruction="分析財務數據與尋找營收增長點與利潤率趨勢 (Extract revenue and margin trends).",
            tier="smart",
            user_id=user_id,
            use_cache=use_cache,
            ttl_hours=ttl
        )
        self.risk_scanner = FundamentalSubAgent(
            name="RiskFactorScanner", 
            instruction="掃描新聞與財報中的風險因子 (Scan for risk factors).",
            tier="fast",
            user_id=user_id,
            use_cache=use_cache,
            ttl_hours=ttl
        )
        self.valuation_modeler = FundamentalSubAgent(
            name="ValuationModeler", 
            instruction="建立估值模型判斷價格是否合理 (Build valuation model).",
            tier="adv",
            user_id=user_id,
            use_cache=use_cache,
            ttl_hours=ttl
        )
        
        self.register_agent("col_smart", self.revenue_extractor)
        self.register_agent("col_fast", self.risk_scanner)
        self.register_agent("col_adv", self.valuation_modeler)
        
    async def run(self, context: Any) -> str:
        tickers = context.get("tickers", [])
        single_ticker = context.get("ticker", "UNKNOWN")
        if not tickers and single_ticker != "UNKNOWN":
            tickers = [single_ticker]
            
        market_data = context.get("market_data", {})
        reports = []
        sc_service = SupplyChainService(user_id=self.user_id)
        
        for t in tickers:
            t_data = market_data.get(t, {}) if market_data else context
            fin = t_data.get("financials", {})
            news = t_data.get("news", [])
            sc_info = sc_service.get_shortage_premium(t)
            
            wrapped_ctx = {
                "user_request": f"Analyze fundamentals for {t}.",
                "data": {
                    "ticker": t,
                    "financials": fin,
                    "news": news,
                    "shortage_premium": sc_info.get("narrative", ""),
                }
            }
            try:
                res = await super().run(wrapped_ctx)
                reports.append(f"### {t} Fundamental Swarm Analysis\n{res}")
            except Exception as e:
                logger.error(f"FundamentalSwarm failed for {t}: {e}")
                reports.append(f"### {t} Analysis\nError: {e}")
        return "\n\n".join(reports)
