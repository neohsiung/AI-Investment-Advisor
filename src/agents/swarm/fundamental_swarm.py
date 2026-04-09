import json
import typing
from typing import List, Dict, Tuple, Any, Optional, Callable, Any
from src.utils.logger import setup_logger
from src.agents.base_agent import BaseAgent
from .role_swarm_base import RoleSwarmBase
from src.services.supply_chain_service import SupplyChainService

logger = setup_logger("FundamentalSwarm")

class FundamentalSubAgent(BaseAgent):
    def __init__(self, name: str, instruction: str, tier: str, **kwargs):
        super().__init__(name=name, prompt_path="prompts/common/default_system.j2", tier=tier, **kwargs)
        self.instruction = instruction

    def run(self, context: Any) -> str:
        ctx_dump = json.dumps(context, indent=2, ensure_ascii=False) if isinstance(context, dict) else str(context)
        prompt_data = {
            "user_request": f"{self.instruction}\n\nData Context:\n{ctx_dump}"
        }
        return self.run_tool_loop(context=prompt_data)

class FundamentalSwarm(RoleSwarmBase):
    def __init__(self, use_cache=True, ttl_hours=None, **kwargs):
        ttl = ttl_hours if ttl_hours is not None else 24
        user_id = kwargs.pop("user_id", None)
        if not user_id:
            raise ValueError("FundamentalSwarm: user_id is required.")
        # Ensure tier is passed to base agent for factory consistency
        kwargs['tier'] = 'smart'
        super().__init__(name="FundamentalSwarm", use_cache=use_cache, ttl_hours=ttl, user_id=user_id, **kwargs)
        
        self.register_sub_agent(
            tier="smart",
            agent=FundamentalSubAgent(
                name="RevenueExtractor", 
                instruction="分析財務數據與尋找營收增長點與利潤率趨勢 (Extract revenue and margin trends).",
                tier="smart",
                user_id=user_id,
                use_cache=use_cache,
                ttl_hours=ttl
            )
        )
        self.register_sub_agent(
            tier="fast",
            agent=FundamentalSubAgent(
                name="RiskFactorScanner", 
                instruction="掃描新聞與財報中的風險因子 (Scan for risk factors).",
                tier="fast",
                user_id=user_id,
                use_cache=use_cache,
                ttl_hours=ttl
            )
        )
        self.register_sub_agent(
            tier="advanced",
            agent=FundamentalSubAgent(
                name="ValuationModeler", 
                instruction="建立估值模型判斷價格是否合理 (Build valuation model).",
                tier="adv",
                user_id=user_id,
                use_cache=use_cache,
                ttl_hours=ttl
            )
        )
        
    def run(self, context: Any) -> str:
        """
        Processes one or more tickers using the parallel swarm engine.
        """
        import asyncio
        tickers = context.get("tickers", [])
        single_ticker = context.get("ticker", "UNKNOWN")
        if not tickers and single_ticker != "UNKNOWN":
            tickers = [single_ticker]
            
        if not tickers:
            return "No tickers provided for analysis."

        reports = []
        sc_service = SupplyChainService(user_id=self.user_id)
        
        # Ensure async loop is ready
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
        import nest_asyncio
        nest_asyncio.apply()

        for t in tickers:
            logger.info(f"FundamentalSwarm: Starting swarm analysis for {t}")
            # Prepare specific context for this ticker
            t_ctx = context.copy()
            t_ctx["ticker"] = t
            t_ctx["user_request"] = f"Analyze fundamentals for {t}."
            
            # Add supply chain context if available
            try:
                sc_info = sc_service.get_shortage_premium(t)
                t_ctx["shortage_premium"] = sc_info.get("narrative", "")
            except Exception:
                pass

            try:
                # Call the new parallel swarm engine
                res = loop.run_until_complete(self.run_swarm(t_ctx))
                reports.append(f"### {t} Fundamental Swarm Analysis\n{res}")
            except Exception as e:
                logger.error(f"FundamentalSwarm failed for {t}: {e}")
                reports.append(f"### {t} Analysis\nError: {e}")

        return "\n\n".join(reports)
