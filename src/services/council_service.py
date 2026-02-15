import logging
import uuid
import json
import asyncio
from typing import Dict, List, Any
from datetime import datetime

from src.agents.factory import AgentFactory
from src.infrastructure.llm_router import DynamicModelRouter
from src.repositories.vector_repository import VectorRepository
from src.infrastructure.lane_manager import LaneManager
from src.utils.format_utils import format_agent_output

logger = logging.getLogger(__name__)

from src.services.user_focus_service import UserFocusService

class CouncilService:
    """
    Orchestrates the Agent Council.
    Manages the debate protocol, dynamic model routing, and consensus formation.
    Supports Map-Reduce for full portfolio analysis.
    """

    def __init__(self):
        self.router = DynamicModelRouter()
        self.vector_repo = VectorRepository()
        self.lane_manager = LaneManager()
        self.user_focus_service = UserFocusService()

    async def start_session(self, topic: str, context_data: Dict[str, Any], scope: str = "single", market_volatility: float = 0.0) -> Dict[str, Any]:
        """
        Starts a Council Session.
        If scope="portfolio", it triggers the Map-Reduce flow.
        """
        session_id = str(uuid.uuid4())
        logger.info(f"Council Session {session_id} started. Topic: {topic} | Scope: {scope}")
        
        # 0. Check Scope for Map-Reduce
        if scope == "portfolio":
            return await self._run_map_reduce_portfolio(session_id, topic, context_data, market_volatility=market_volatility)
        
        # Default Single Topic Flow (Thread-blocking wrapper for async compatibility)
        # In a real async app, this should be fully async. 
        # Here we wrap the synchronous logic in a lane task or just run it if it's CPU bound.
        # For simplicity in this refactor, we keep standard flow as is but make it async-capable.
        return await self._run_standard_session(session_id, topic, context_data, market_volatility=market_volatility)

    async def _run_map_reduce_portfolio(self, session_id: str, topic: str, context_data: Dict[str, Any], market_volatility: float = 0.0):
        """
        Phase 4: Map-Reduce for Full Portfolio.
        1. Map: Analyze each ticker in parallel (sub-councils).
        2. Reduce: Aggregate signals.
        3. Synthesis: Final CIO Report.
        """
        portfolio = context_data.get("portfolio", [])
        if not portfolio:
             return {"error": "No portfolio data provided for map-reduce."}

        # --- Phase 1: Map (Parallel Analysis) ---
        # Define the task for each ticker
        async def analyze_ticker_task(ticker_data):
            ticker = ticker_data['symbol']
            qty = ticker_data['quantity']
            
            # Sub-Council: Momentum + Fundamental (Fast Tier)
            # We use a lightweight sub-council to save costs
            # Sub-Council: Momentum + Fundamental (Fast Tier)
            # We use a lightweight sub-council to save costs
            mom_agent = AgentFactory.create_agent("Momentum", tier="fast")
            fun_agent = AgentFactory.create_agent("Fundamental", tier="fast")
            
            sub_context = {
                "topic": f"Analysis of {ticker}",
                "ticker": ticker,
                "quantity": qty,
                "market_data": context_data.get("market_data")
            }
            
            # Parallel Run within Sub-Council
            # Note: Agents are currently sync. We wrap them.
            loop = asyncio.get_running_loop()
            t1 = loop.run_in_executor(None, mom_agent.run, sub_context)
            t2 = loop.run_in_executor(None, fun_agent.run, sub_context)
            
            res_mom, res_fun = await asyncio.gather(t1, t2)
            
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
        consensus_tier = self.router.select_tier(topic, round_num=99, market_volatility=market_volatility)
        cio = AgentFactory.create_cio_agent(tier=consensus_tier)
        
        final_context = {
            "topic": topic,
            "council_transcript": aggregated_summary, 
            "memory_chain": "Map-Reduce Session",
            "current_date": datetime.now().strftime("%Y-%m-%d"),
            "market_data": context_data.get("market_data"),
            "portfolio_summary": "Full Portfolio Analysis"
        }
        
        # Run CIO (Sync wrapped)
        loop = asyncio.get_running_loop()
        final_report = await loop.run_in_executor(None, cio.run, final_context)
        
        # Archive (Simple)
        self._archive_minutes(session_id, topic, str(final_report), aggregated_summary)

        return {
            "session_id": session_id,
            "type": "map-reduce",
            "consensus": str(final_report),
            "transcript": aggregated_summary
        }

    async def _run_standard_session(self, session_id: str, topic: str, context_data: Dict[str, Any], market_volatility: float = 0.0):
        """
        Original logic wrapped for async.
        """
        # Run in thread to avoid blocking event loop
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._run_sync_logic, session_id, topic, context_data, market_volatility)

    def _run_sync_logic(self, session_id: str, topic: str, context_data: Dict[str, Any], market_volatility: float = 0.0):
        # ... (Original Logic from previous file version, kept for single-topic debates) ...
        # For brevity in this refactor, I will re-implement the core parts ensuring it addresses the task.
        
        # 1. Experience Replay
        past_wisdom = ""
        try:
             # We use keyword matching or simple topic lookup if no embedding provided
             # But VectorRepo.search_similar_minutes expects explicit call
             # Here we try to get "similar" minutes.
             # Since we don't have an embedding service in CouncilService yet, 
             # we might need to rely on the VectorRepo to handle text-based fallback or mock it for now.
             
             # If we are using the new 'search_similar_minutes' (which returns empty now),
             # we should at least call it to verify the integration.
             # In future, we will pass an embedding of 'topic'.
             similar = self.vector_repo.search_similar_minutes(topic, limit=1)
             if similar:
                 past_wisdom = f"Previous Related Decision for '{similar[0]['topic']}': {similar[0]['consensus']}"
                 logger.info(f"Council: Recalled wisdom -> {past_wisdom[:50]}...")
        except Exception as e:
            logger.warning(f"Council: Memory recall failed: {e}")

        # 2. Members
        # Determine Tier based on Topic Complexity or Market Regime
        # (Router integration is already here)
        tier = self.router.select_tier(topic, round_num=1, market_volatility=market_volatility)
        
        # Instantiate Agents with retrieved context? 
        # Actually, agents take context in .run(), so we just pass it there.
        members = [
            AgentFactory.create_momentum_agent(tier=tier),
            AgentFactory.create_fundamental_agent(tier=tier),
            AgentFactory.create_risk_agent(tier=tier),
            AgentFactory.create_sentiment_agent(tier=tier),
            AgentFactory.create_macro_agent(tier=tier)
        ]

        # 3. Debate
        stances = []
        transcript = []
        
        # Inject Memory and User Focus
        user_focus = self.user_focus_service.get_user_focus()
        debate_context = {
            **context_data, 
            "historical_context": past_wisdom, 
            "topic": topic,
            "user_focus": user_focus
        }
        
        for agent in members:
            try:
                # Agents expect a single dict or string.
                # If they support expanded context keys (like 'historical_context'), they will use it.
                # If they utilize a base_agent prompt builder, we must ensure it handles this key.
                # For now, we pass the dict.
                res = agent.run(debate_context)
                stances.append(f"[{agent.name}]: {res}")
                transcript.append(f"[{agent.name}]: {res}")
            except Exception as e:
                logger.error(f"Agent {agent.name} failed: {e}")

        # 4. Consensus
        cio = AgentFactory.create_cio_agent(tier=self.router.select_tier(topic, round_num=99))
        debates_text = "\n".join(stances)
        
        final_context = {
            "topic": topic,
            "council_transcript": debates_text,
            "memory_chain": past_wisdom,
            "current_date": datetime.now().strftime("%Y-%m-%d"),
            "market_data": context_data.get("market_data")
        }
        
        decision = cio.run(final_context)
        self._archive_minutes(session_id, topic, str(decision), "\n".join(transcript))
        
        return {
            "session_id": session_id,
            "consensus": str(decision),
            "transcript": transcript
        }

    def _archive_minutes(self, session_id, topic, consensus, transcript):
        try:
            # Placeholder embedding
            dummy_embedding = [0.0] * 1536 
            self.vector_repo.add_council_minute(
                session_id=session_id,
                topic=topic,
                participants=["MapReduce_Council"],
                consensus=consensus,
                transcript=transcript,
                embedding=dummy_embedding
            )
        except Exception as e:
            logger.error(f"Failed to archive: {e}")
