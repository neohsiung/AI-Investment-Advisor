from src.utils.logger import setup_logger
logger = setup_logger("CouncilService")

import uuid
import json
import asyncio
import os
import typing
from typing import List, Dict, Tuple, Any, Optional, Callable, Union, Awaitable
from datetime import datetime

from src.infrastructure.llm.tier_router_base import ITierRouter, RoutingContext
from src.infrastructure.llm.council_tier_router import CouncilTierRouter
from src.infrastructure.llm.tier_config import SettingsAwareModelRouter
from src.infrastructure.llm.llm_gateway import OpenRouterGateway
from src.domain.interfaces import Message, LLMConfig
from src.repositories.settings_repository import AlchemySettingsRepository
from src.repositories.vector_repository import AlchemyVectorRepository
from src.infrastructure.lane_manager import LaneManager
from src.utils.format_utils import format_agent_output

from src.services.user_focus_service import UserFocusService
from src.services.settings_service import SettingsService
from src.services.competitor_service import CompetitorService

class CouncilService:
    """
    Orchestrates the Agent Council, including debate protocols and consensus formation.
    協調 Agent 委員會，包含辯論協議與共識達成。
    
    Supports Map-Reduce for full portfolio analysis and dynamic model routing.
    支援用於全投資組合分析的 Map-Reduce 與動態模型路由。
    """

    def __init__(self, user_id: str, settings_service: Optional["SettingsService"] = None,
        tier_router: Optional[ITierRouter] = None,
    ):
        self.user_id = user_id
        # Delayed import to avoid circular dependency
        from src.services.settings_service import SettingsService
        self.settings_service = settings_service or SettingsService(user_id=user_id)
        self.router: ITierRouter = tier_router or CouncilTierRouter()
        self.vector_repo = AlchemyVectorRepository()
        self.lane_manager = LaneManager()
        self.competitor_service = CompetitorService(user_id=user_id)

        # PAD Phase 2: Add model router and gateway
        from src.data.database import get_db_engine
        self.settings_repo = AlchemySettingsRepository(engine=get_db_engine())
        self.model_router = SettingsAwareModelRouter(self.settings_repo)
        self.gateway = OpenRouterGateway()
    
    async def _call_agent_llm(self, agent_name: str, context: Dict[str, Any], tier: str = "smart", 
                              temperature: float = 0.7, max_tokens: int = 2000) -> str:
        """
        PAD Phase 2: Replace AgentFactory.create_*_agent().run() with direct gateway calls.
        Generic method to call LLM for any agent role.
        """
        try:
            from src.infrastructure.llm.llm_config_chain import build_config_chain
            from src.infrastructure.llm.resilient_pipeline import ResilientLLMPipeline

            chain = build_config_chain(self.user_id, tier)
            if not chain:
                raise ValueError(f"No model configured for tier={tier} user={self.user_id}")

            pipeline = ResilientLLMPipeline(config_chain=chain)

            from src.utils.prompt_utils import load_agent_prompt

            # [Rule #13] Dynamic 指標原則: Load system prompt from prompts/*.txt instead of hardcoded strings
            system_prompt = load_agent_prompt(agent_name)
            
            messages = [
                Message(role="system", content=system_prompt),
                Message(role="user", content=json.dumps(context))
            ]

            logger.debug(f"Council: Calling {agent_name} agent via tier={tier} (user={self.user_id})")
            response, _ = await pipeline.execute(messages, temperature=temperature, max_tokens=max_tokens)

            if not isinstance(response, str):
                raise ValueError(f"Unexpected response type from pipeline: {type(response)}")

            return response
        except Exception as e:
            logger.error(f"Council: {agent_name} agent failed: {e}")
            raise

    async def start_session(self, topic: str, context_data: Dict[str, Any], user_id: str, scope: str = "single", market_volatility: float = 0.0, mode: str = "weekly") -> Dict[str, Any]:
        """
        Starts a high-level Council Session.
        啟動高階委員會議程。
        
        If scope="portfolio", it triggers the Map-Reduce flow.
        若 scope="portfolio"，則觸發 Map-Reduce 流程。
        """
        session_id = str(uuid.uuid4())
        logger.info(f"Council Session {session_id} started. Topic: {topic} | Scope: {scope} | User: {user_id}")
        
        # 0. Check Scope for Map-Reduce
        if scope == "portfolio":
            return await self._run_map_reduce_portfolio(session_id, topic, context_data, market_volatility=market_volatility, user_id=user_id, mode=mode)
        
        # Default Single Topic Flow (Thread-blocking wrapper for async compatibility)
        return await self._run_standard_session(session_id, topic, context_data, market_volatility=market_volatility, user_id=user_id, mode=mode)

    async def _run_map_reduce_portfolio(self, session_id: str, topic: str, context_data: Dict[str, Any], user_id: str, market_volatility: float = 0.0, mode: str = "weekly") -> Dict[str, Any]:
        """
        Phase 4: Map-Reduce execution for full portfolio analysis.
        第四階段：針對全投資組合分析的 Map-Reduce 執行。
        """
        portfolio = context_data.get("portfolio", [])
        if not portfolio:
             return {"error": "No portfolio data provided for map-reduce."}

        # --- Phase 1: Map (Parallel Analysis) ---
        # Define the task for each ticker
        async def analyze_ticker_task(ticker_data):
            ticker = ticker_data['symbol']
            qty = ticker_data['quantity']
            
            sub_context = {
                "topic": f"Analysis of {ticker}",
                "ticker": ticker,
                "quantity": qty,
                "market_data": context_data.get("market_data")
            }
            
            # Parallel Run within Sub-Council - Directly await since agents are async
            # PAD Phase 2: Replace AgentFactory calls with _call_agent_llm
            res_mom, res_fun = await asyncio.gather(
                self._call_agent_llm("Momentum", sub_context, tier="fast"),
                self._call_agent_llm("Fundamental", sub_context, tier="fast")
            )
            
            return {
                "ticker": ticker,
                "momentum": res_mom,
                "fundamental": res_fun,
                "quantity": qty
            }

        # Create tasks
        tasks = [lambda t=t: analyze_ticker_task(t) for t in portfolio]
        
        # Execute Batch via LaneManager
        logger.info(f"Map-Reduce: Starting analysis for {len(portfolio)} tickers...")
        map_results = await self.lane_manager.run_batch(tasks, batch_size=5)
        
        # --- Phase 2: Reduce (Aggregation) ---
        aggregated_summary = "## 2. 議會焦點辯論 (The Great Debate & Detailed Analysis)\n"
        for res in map_results:
            if isinstance(res, dict) and "ticker" in res:
                aggregated_summary += f"#### {res['ticker']} (Qty: {res['quantity']})\n"
                aggregated_summary += f"- **Momentum**: {format_agent_output(res['momentum'])}\n"
                aggregated_summary += f"- **Fundamental**: {format_agent_output(res['fundamental'])}\n\n"
            else:
                aggregated_summary += f"- Error in analysis: {res}\n"

        # --- Phase 3: Synthesis (CIO) ---
        # Level 1-2 Consensus
        consensus_tier = self.router.select_tier(
            RoutingContext(topic=topic, round_num=99, market_volatility=market_volatility, user_id=self.user_id)
        )
        
        final_context = {
            "topic": topic,
            "council_transcript": aggregated_summary, 
            "memory_chain": "Map-Reduce Session",
            "current_date": datetime.now().strftime("%Y-%m-%d"),
            "market_data": context_data.get("market_data"),
            "portfolio_summary": "Full Portfolio Analysis"
        }
        
        # Run CIO (Async) - PAD Phase 2: Replace AgentFactory with _call_agent_llm
        final_report = await self._call_agent_llm("CIO", final_context, tier=consensus_tier)
        
        # Archive (Simple)
        self._archive_minutes(user_id, session_id, topic, str(final_report), aggregated_summary)

        return {
            "session_id": session_id,
            "type": "map-reduce",
            "consensus": str(final_report),
            "transcript": aggregated_summary
        }

    async def _run_standard_session(self, session_id: str, topic: str, context_data: Dict[str, Any], user_id: str, market_volatility: float = 0.0, mode: str = "weekly") -> Dict[str, Any]:
        """
        Standard single-topic Council session (Async).
        標準單一主題委員會議程 (非同步)。
        """
        return await self._run_debate_logic(session_id, topic, context_data, user_id, market_volatility, mode)

    async def _run_debate_logic(self, session_id: str, topic: str, context_data: Dict[str, Any], user_id: str, market_volatility: float = 0.0, mode: str = "weekly") -> Dict[str, Any]:
        """
        Core asynchronous logic for running an agent debate and capturing the transcript.
        執行 Agent 辯論並記錄逐字稿的核心非同步邏輯。
        """
        
        # 1. Experience Replay
        past_wisdom = ""
        try:
             similar = self.vector_repo.search_similar_minutes(topic, limit=1)
             if similar:
                 past_wisdom = f"Previous Related Decision for '{similar[0]['topic']}': {similar[0]['consensus']}"
                 logger.info(f"Council: Recalled wisdom -> {past_wisdom[:50]}...")
        except Exception as e:
            logger.warning(f"Council: Memory recall failed: {e}")

        # 2. Members
        # 1. Start Initial Debate
        tier = self.router.select_tier(
            RoutingContext(topic=topic, round_num=1, market_volatility=market_volatility, user_id=self.user_id)
        )
        
        # Instantiate Agents with retrieved context
        # [Fix] Wrap in try-except to prevent one agent failure from crashing the whole council
        # PAD Phase 2: Remove agent instantiation; we'll call via _call_agent_llm
        agent_names = ["Momentum", "Fundamental", "Risk", "Sentiment", "Macro"]

        # 3. Debate
        stances = []
        transcript = []
        
        # Inject Memory and User Focus
        # v5.0: Instantiate UserFocusService with the correct user_id
        uf_service = UserFocusService(user_id=user_id, settings_service=self.settings_service)
        user_focus = uf_service.get_user_focus()
        
        # [NEW] v4.5.1: Competitor Penetration check for leaders
        competitor_analysis = None
        # Extract ticker from topic (assuming topic like "Analysis of TSLA")
        # Simplified: Check if any peer group leader is in the topic
        for leader in self.competitor_service.PEER_GROUPS.keys():
            if leader in topic.upper():
                competitor_analysis = self.competitor_service.analyze_penetration(leader)
                logger.info(f"Council: Injected competitor analysis for {leader}")
                break

        debate_context = {
            **context_data, 
            "historical_context": past_wisdom, 
            "topic": topic,
            "user_focus": user_focus,
            "competitor_analysis": competitor_analysis
        }
        
        # PAD Phase 2: Replace agent.run() with _call_agent_llm
        for agent_name in agent_names:
            try:
                logger.debug(f"Council: Running agent {agent_name}...")
                res = await self._call_agent_llm(agent_name, debate_context, tier=tier)
                stances.append(f"[{agent_name}]: {res}")
                transcript.append(f"[{agent_name}]: {res}")
            except Exception as e:
                logger.error(f"Agent {agent_name} failed during debate: {e}")
                transcript.append(f"[{agent_name}]: Error - {e}")

        # 4. Final CIO Consensus
        consensus_tier = self.router.select_tier(
            RoutingContext(topic=topic, round_num=99, user_id=self.user_id)
        )
        debates_text = "\n".join(stances)
        
        # Determine if Structural Cooling was detected by MacroAgent
        fractal_debate_rules = ""
        if "Structural Cooling Detected" in debates_text:
             fractal_debate_rules = "FRACTAL RULE APPLIED: Structural Cooling detected. Systematically reduce weight of traditional cyclical stocks (e.g., industrials, materials) and increase weight of software/infrastructure moats."
        
        final_context = {
            "topic": topic,
            "council_transcript": debates_text,
            "council_directive": context_data.get("msg_prefix", ""),
            "memory_chain": past_wisdom,
            "current_date": datetime.now().strftime("%Y-%m-%d"),
            "market_data": context_data.get("market_data"),
            "fractal_debate_rules": fractal_debate_rules,
            "competitor_analysis": competitor_analysis
        }
        
        try:
            # v9.1: High-verbosity logging for cio context to debug consensus issues
            logger.info(f"Council: Launching CIO Consensus for topic: {topic}")
            logger.debug(f"Council: CIO Final Context Keys: {list(final_context.keys())}")
            
            # PAD Phase 2: Replace AgentFactory with _call_agent_llm
            decision = await self._call_agent_llm("CIO", final_context, tier=consensus_tier)
            
            if not decision:
                logger.warning("Council: CIO response was empty.")
                decision = "Council reached no consensus (Empty response)."
                
        except Exception as e:
            # Log full context only on error to avoid bloating logs
            logger.error(f"Council: CIO agent failed: {e}", exc_info=True)
            logger.error(f"Council DEBUG - Final Context attempted: {final_context}")
            decision = f"Consensus failed due to internal error: {e}. Please review transcripts below."
        
        self._archive_minutes(user_id, session_id, topic, str(decision), "\n".join(transcript))
        
        return {
            "session_id": session_id,
            "consensus": str(decision),
            "transcript": transcript
        }

    def _archive_minutes(self, user_id: str, session_id: str, topic: str, consensus: str, transcript: str) -> None:
        """
        Archive the session results to the vector repository for experience replay.
        將議程結果歸檔至向量儲存庫，以便進行復盤 (Experience Replay)。
        """
        try:
            # Placeholder embedding
            dummy_embedding = [0.0] * 1536 
            self.vector_repo.add_council_minute(
                user_id=user_id,
                session_id=session_id,
                topic=topic,
                participants=["MapReduce_Council"],
                consensus=consensus,
                transcript=transcript,
                embedding=dummy_embedding
            )
        except Exception as e:
            logger.error(f"Failed to archive: {e}")
