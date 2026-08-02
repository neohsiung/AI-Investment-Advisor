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
        # P1 learning loop (2026-07-11): decision->outcome memory, alpha-anchored
        # reflection. Replaces the self-graded analyze_narrative_drift pattern.
        from src.services.outcome_reflection_service import OutcomeReflectionService
        self.outcome_service = OutcomeReflectionService(user_id=user_id)

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

            pipeline = ResilientLLMPipeline(
                config_chain=chain,
                user_id=self.user_id,
                agent_name=agent_name,
                tier=tier,
            )

            from src.utils.prompt_utils import load_agent_prompt

            # [Rule #13] Dynamic 指標原則: Load system prompt from prompts/*.txt instead of hardcoded strings
            system_prompt = load_agent_prompt(agent_name)
            
            try:
                from src.repositories.memory_repository import AgentState
                agent_state = AgentState()
                rules = agent_state.load_general_rules(agent_name, user_id=self.user_id)
                if rules:
                    system_prompt += f"\n\n## Dynamic Rules (derived from past outcomes):\n{rules}"
            except Exception as re_err:
                logger.debug(f"Council: failed to load AgentState for {agent_name} (non-blocking): {re_err}")

            # B-P2.2 (2026-07-14): inject the learned user-preference summary
            # (risk appetite, sector aversions, position-size comfort) at
            # the synthesis step only — not every sub-agent call, to avoid
            # diluting the signal and adding a DB round-trip per agent.
            if agent_name in ("CIO", "CouncilSynthesis"):
                try:
                    from src.services.user_preference_service import UserPreferenceService
                    pref_summary = UserPreferenceService(self.user_id).get_summary_text()
                    if pref_summary:
                        system_prompt += f"\n\n## User Preference Profile (learned from past approve/reject decisions):\n{pref_summary}"
                except Exception as pref_e:
                    logger.debug(f"Council: failed to load user preferences (non-blocking): {pref_e}")
            
            messages = [
                Message(role="system", content=system_prompt),
                Message(role="user", content=json.dumps(context))
            ]

            logger.debug(f"Council: Calling {agent_name} agent via tier={tier} (user={self.user_id})")
            try:
                response, _ = await pipeline.execute(messages, temperature=temperature, max_tokens=max_tokens)
            except Exception as pipeline_err:
                if tier != "fast":
                    logger.warning(f"Council: {agent_name} agent execution failed on tier {tier} ({pipeline_err}). Gracefully falling back to fast tier...")
                    try:
                        fast_chain = build_config_chain(self.user_id, "fast")
                        if fast_chain:
                            fast_pipeline = ResilientLLMPipeline(
                                config_chain=fast_chain,
                                user_id=self.user_id,
                                agent_name=agent_name,
                                tier="fast",
                            )
                            response, _ = await fast_pipeline.execute(messages, temperature=temperature, max_tokens=max_tokens)
                        else:
                            raise pipeline_err
                    except Exception as fast_err:
                        logger.error(f"Council: {agent_name} fallback to fast tier failed as well: {fast_err}")
                        raise pipeline_err
                else:
                    raise

            if not isinstance(response, str):
                raise ValueError(f"Unexpected response type from pipeline: {type(response)}")

            return response
        except Exception as e:
            logger.error(f"Council: {agent_name} agent failed: {e}")
            raise

    _PAST_WISDOM_COMPACT_THRESHOLD_CHARS = 1200  # ~300 tokens

    async def _compact_past_wisdom(self, minutes: List[Dict[str, Any]]) -> str:
        """
        Join up to k recalled council minutes into a single context block.
        If the naive join would blow the debate prompt's memory budget,
        compress it with a nano-tier call instead of truncating blindly.
        """
        lines = [f"- [{m['topic']}]: {m['consensus']}" for m in minutes if m.get('consensus')]
        joined = "Previous related decisions:\n" + "\n".join(lines)
        if len(joined) <= self._PAST_WISDOM_COMPACT_THRESHOLD_CHARS:
            return joined

        try:
            from src.infrastructure.llm.llm_config_chain import build_config_chain
            from src.infrastructure.llm.resilient_pipeline import ResilientLLMPipeline
            from src.domain.interfaces import Message

            chain = build_config_chain(self.user_id, "nano")
            if not chain:
                return joined[:self._PAST_WISDOM_COMPACT_THRESHOLD_CHARS]
            pipeline = ResilientLLMPipeline(
                config_chain=chain, user_id=self.user_id,
                agent_name="PastWisdomCompactor", tier="nano",
            )
            prompt = (
                "Compress the following past investment decisions into a single "
                "dense paragraph (~300 tokens max), preserving tickers, signals, "
                "and any stated reasons. Output only the paragraph.\n\n" + joined
            )
            compacted, _ = await pipeline.execute(
                [Message(role="user", content=prompt)], temperature=0.2, max_tokens=400
            )
            return compacted.strip() if compacted else joined[:self._PAST_WISDOM_COMPACT_THRESHOLD_CHARS]
        except Exception as e:
            logger.debug(f"Council: past-wisdom compaction failed, truncating instead: {e}")
            return joined[:self._PAST_WISDOM_COMPACT_THRESHOLD_CHARS]

    async def _verify_grounding(self, decision_text: str, market_data: Optional[Dict[str, Any]]) -> str:
        """
        P3.2 (2026-07-11): independent fact-verifier (financial-services critic
        pattern). Re-checks numeric claims in the final decision against the
        real fetched market_data (price/indicators/factors), flagging figures
        that don't match anything in the source data — catches hallucinated
        numbers before they reach the user. Read-only, non-blocking: any
        failure here just skips verification rather than blocking the decision.
        """
        if not decision_text or not market_data:
            return ""
        try:
            prompt = (
                "You are an independent verifier. Re-check every specific numeric "
                "claim (prices, percentages, targets) in the DECISION below against "
                "the SOURCE DATA. Do not re-analyze the investment thesis — only "
                "check whether cited numbers are consistent with source data or "
                "plausible given it. List any figure that appears fabricated or "
                "inconsistent with source data. If everything checks out, say "
                "'No grounding issues found.'\n\n"
                f"DECISION:\n{decision_text}\n\nSOURCE DATA:\n{json.dumps(market_data, default=str)[:4000]}"
            )
            note = await self._call_agent_llm("Verifier", {"instruction": prompt}, tier="fast", max_tokens=300)
            return str(note or "")
        except Exception as e:
            logger.debug(f"Council: grounding verification skipped (non-blocking): {e}")
            return ""

    async def _call_structured(self, agent_name: str, prompt: str, schema, tier: str = "fast",
                                temperature: float = 0.3, max_tokens: int = 400):
        """
        Structured-output variant of _call_agent_llm (P0.2). Uses the primary
        candidate's raw gateway directly (no fallback chain) since this backs
        a non-critical synthesis step (decision recording); on any failure
        returns None and callers should skip rather than block the council.
        """
        try:
            from src.infrastructure.llm.llm_config_chain import build_config_chain
            from src.infrastructure.llm.resilient_pipeline import ResilientLLMPipeline
            from src.agents.structured import invoke_structured

            chain = build_config_chain(self.user_id, tier)
            if not chain:
                return None
            pipeline = ResilientLLMPipeline(config_chain=chain, user_id=self.user_id,
                                             agent_name=agent_name, tier=tier)
            gateway = pipeline._gateway_factory(chain[0])
            config = pipeline._build_llm_config(chain[0], temperature=temperature, max_tokens=max_tokens)
            parsed, _raw = await invoke_structured(gateway, [Message(role="user", content=prompt)], config, schema)
            return parsed
        except Exception as e:
            logger.debug(f"Council: structured call for {agent_name} failed (non-blocking): {e}")
            return None

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
        Re-engineered as a Multi-Agent DAG workflow engine with node-level caching.
        """
        portfolio = context_data.get("portfolio", [])
        if not portfolio:
             return {"error": "No portfolio data provided for map-reduce."}

        logger.info(f"Re-engineered Map-Reduce (DAG): Analyzing portfolio for user {user_id}...")

        # Initialize multi-level Cache and DAG Executor
        from src.infrastructure.workflow.cache import WorkflowCache
        from src.infrastructure.workflow.executor import DAGExecutor
        from src.infrastructure.workflow.portfolio_dag import PortfolioAnalysisDAG

        cache = WorkflowCache()
        dag = PortfolioAnalysisDAG(cache=cache)
        executor = DAGExecutor(dag.nodes, cache=cache)

        # Select the dynamic tier based on market volatility and user routing rules
        consensus_tier = self.router.select_tier(
            RoutingContext(topic=topic, round_num=99, market_volatility=market_volatility, user_id=user_id)
        )

        # Configure DAG initial inputs and context payload
        initial_inputs = {
            "portfolio": portfolio,
            "topic": topic
        }
        
        # Context dict that passes services and context properties to nodes
        context = {
            "user_id": user_id,
            "session_id": session_id,
            "council_service": self,
            "initial_market_data": context_data.get("market_data", {}),
            "workflow_cache": cache,
            "telemetry": [],
            "consensus_tier": consensus_tier
        }

        # Execute the DAG workflow
        try:
            flow_data = await executor.execute(initial_inputs, context)
        except Exception as e:
            logger.error(f"Re-engineered Map-Reduce (DAG) failed: {e}", exc_info=True)
            raise e

        # Extract final outputs from DAG flow_data
        final_report = flow_data.get("final_report", "")
        aggregated_summary = flow_data.get("aggregated_summary", "")
        grounding_note = flow_data.get("verifier_note", "")

        # Archive (Simple)
        self._archive_minutes(user_id, session_id, topic, str(final_report), aggregated_summary)

        # Cold Processing Backup
        try:
            await self._write_cold_backup(user_id, session_id, topic, str(final_report), str(grounding_note))
        except Exception as e:
            logger.warning(f"Cold Backup: failed to write: {e}")

        return {
            "session_id": session_id,
            "type": "map-reduce",
            "consensus": str(final_report),
            "transcript": aggregated_summary,
            "grounding_check": grounding_note,
        }

    async def _run_standard_session(self, session_id: str, topic: str, context_data: Dict[str, Any], user_id: str, market_volatility: float = 0.0, mode: str = "weekly") -> Dict[str, Any]:
        """
        Standard single-topic Council session, re-engineered as a DAG workflow.
        10 agents run in parallel → ReduceDebateStances → CIODraft → RiskChallenge → CIOFinal → Verifier.
        """
        logger.info(f"Re-engineered Standard Session (DAG): topic={topic}, user={user_id}")

        # ── 1. Pre-compute enrichment context (same as legacy _run_debate_logic) ──
        past_wisdom = ""
        try:
            similar = []
            try:
                from src.infrastructure.llm.embedding_service import embed_text
                q_emb = embed_text(topic)
                if q_emb:
                    similar = self.vector_repo.search_similar_minutes_by_embedding(q_emb, user_id=self.user_id, limit=5)
            except Exception as emb_e:
                logger.debug(f"Council: semantic recall unavailable ({emb_e}); using text search")
            if not similar:
                similar = self.vector_repo.search_similar_minutes(topic, user_id=self.user_id, limit=5)
            if similar:
                past_wisdom = await self._compact_past_wisdom(similar)
                logger.info(f"Council: Recalled {len(similar)} past minute(s) -> {past_wisdom[:50]}...")
        except Exception as e:
            logger.warning(f"Council: Memory recall failed: {e}")

        # User focus & competitor analysis
        uf_service = UserFocusService(user_id=user_id, settings_service=self.settings_service)
        user_focus = uf_service.get_user_focus()

        competitor_analysis = None
        for leader in self.competitor_service.PEER_GROUPS.keys():
            if leader in topic.upper():
                competitor_analysis = await self.competitor_service.analyze_penetration(leader)
                logger.info(f"Council: Injected competitor analysis for {leader}")
                break

        _topic_ticker = None
        for _word in topic.upper().replace(",", " ").split():
            if 1 < len(_word) <= 5 and _word.isalpha():
                _topic_ticker = _word
                break
        past_decision_lessons = self.outcome_service.get_past_context(ticker=_topic_ticker, limit=3)

        # ── 2. Build enriched debate_context dict for all agents ──
        debate_context = {
            **context_data,
            "historical_context": past_wisdom,
            "topic": topic,
            "user_focus": user_focus,
            "competitor_analysis": competitor_analysis,
            "past_decision_lessons": past_decision_lessons or "No prior resolved decisions yet.",
        }

        # ── 3. Select dynamic consensus tier ──
        consensus_tier = self.router.select_tier(
            RoutingContext(topic=topic, round_num=99, market_volatility=market_volatility, user_id=user_id)
        )

        # ── 4. Initialize DAG and Executor ──
        from src.infrastructure.workflow.cache import WorkflowCache
        from src.infrastructure.workflow.executor import DAGExecutor
        from src.infrastructure.workflow.portfolio_dag import SingleTickerAnalysisDAG

        cache = WorkflowCache()
        dag = SingleTickerAnalysisDAG(cache=cache)
        executor = DAGExecutor(dag.nodes, cache=cache)

        initial_inputs = {
            "topic": topic,
            "debate_context": debate_context,
            "market_data": context_data.get("market_data"),
        }

        context = {
            "user_id": user_id,
            "session_id": session_id,
            "council_service": self,
            "consensus_tier": consensus_tier,
            "telemetry": [],
        }

        # ── 5. Execute the DAG ──
        try:
            flow_data = await executor.execute(initial_inputs, context)
        except Exception as e:
            logger.error(f"Re-engineered Standard Session (DAG) failed: {e}", exc_info=True)
            # Fallback to legacy procedural logic
            logger.warning("Falling back to legacy _run_debate_logic...")
            try:
                return await self._run_debate_logic(session_id, topic, context_data, user_id, market_volatility, mode)
            except Exception as legacy_err:
                logger.error(f"Legacy _run_debate_logic also failed: {legacy_err}. Falling back to L3 Static Fallback...")
                try:
                    similar = self.vector_repo.search_similar_minutes(topic, user_id=user_id, limit=1)
                    if similar:
                        last_minute = similar[0]
                        warning_prefix = (
                            "⚠️ WARNING: All active LLM services are currently offline. "
                            "Displaying the most recent cached decision from database memory.\n\n"
                        )
                        return {
                            "session_id": session_id,
                            "consensus": warning_prefix + last_minute.get("consensus", "No consensus found."),
                            "transcript": [line for line in (last_minute.get("transcript") or "").split("\n") if line.strip()],
                            "grounding_check": "Factual verification skipped (Static Fallback Mode).",
                            "static_fallback": True
                        }
                except Exception as db_e:
                    logger.critical(f"L3 Static Fallback failed to read database: {db_e}")
                raise legacy_err

        # ── 6. Extract results ──
        final_report = flow_data.get("final_report", "")
        council_transcript = flow_data.get("council_transcript", "")
        grounding_note = flow_data.get("verifier_note", "")

        # Build transcript list for compatibility with downstream consumers
        transcript_lines = [line for line in council_transcript.split("\n") if line.strip()]

        # Archive
        self._archive_minutes(user_id, session_id, topic, str(final_report), council_transcript)

        # Cold Processing Backup
        try:
            await self._write_cold_backup(user_id, session_id, topic, str(final_report), str(grounding_note))
        except Exception as e:
            logger.warning(f"Cold Backup: failed to write: {e}")

        return {
            "session_id": session_id,
            "consensus": str(final_report),
            "transcript": transcript_lines,
            "grounding_check": grounding_note,
        }

    async def _run_debate_logic(self, session_id: str, topic: str, context_data: Dict[str, Any], user_id: str, market_volatility: float = 0.0, mode: str = "weekly") -> Dict[str, Any]:
        """
        Core asynchronous logic for running an agent debate and capturing the transcript.
        執行 Agent 辯論並記錄逐字稿的核心非同步邏輯。
        """
        
        # 1. Experience Replay — semantic recall first (real embeddings), then
        # keyword full-text as fallback. (2026-07-11)
        # 2026-07-14: raised k=1 -> k=5 (a single closest match was starving
        # the council of memory) and added user_id isolation (previously
        # searched across every tenant's council_minutes). Multiple
        # recalled minutes are compacted into a single ~300-token block via
        # a nano-tier call so the extra context doesn't blow up the debate
        # prompt budget.
        past_wisdom = ""
        try:
             similar = []
             try:
                 from src.infrastructure.llm.embedding_service import embed_text
                 q_emb = embed_text(topic)
                 if q_emb:
                     similar = self.vector_repo.search_similar_minutes_by_embedding(q_emb, user_id=self.user_id, limit=5)
             except Exception as emb_e:
                 logger.debug(f"Council: semantic recall unavailable ({emb_e}); using text search")
             if not similar:
                 similar = self.vector_repo.search_similar_minutes(topic, user_id=self.user_id, limit=5)
             if similar:
                 past_wisdom = await self._compact_past_wisdom(similar)
                 logger.info(f"Council: Recalled {len(similar)} past minute(s) -> {past_wisdom[:50]}...")
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
        # [B-PLAN] v2.0: 12 核心 Agents（3个 Scout + 7 分析 + CIO + Engineer）
        agent_names = [
            "Macro",
            "Momentum", 
            "Fundamental",
            "Sentiment",
            "Thematic",
            "Risk",
            "Sentinel",
            # Scout agents for buy-side opportunity discovery
            "Momentum Scout",
            "Fundamental Scout",
            "Macro Scout"
        ]

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
                competitor_analysis = await self.competitor_service.analyze_penetration(leader)
                logger.info(f"Council: Injected competitor analysis for {leader}")
                break

        # P1 learning loop: try to extract a ticker from the topic (e.g.
        # "Analysis of TSLA") for same-ticker lessons; always include recent
        # cross-ticker lessons regardless.
        _topic_ticker = None
        for _word in topic.upper().replace(",", " ").split():
            if 1 < len(_word) <= 5 and _word.isalpha():
                _topic_ticker = _word
                break
        past_decision_lessons = self.outcome_service.get_past_context(ticker=_topic_ticker, limit=3)

        debate_context = {
            **context_data,
            "historical_context": past_wisdom,
            "topic": topic,
            "user_focus": user_focus,
            "competitor_analysis": competitor_analysis,
            "past_decision_lessons": past_decision_lessons or "No prior resolved decisions yet.",
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

        # P3.1 (2026-07-11): bounded adversarial round — Risk agent challenges
        # the CIO's draft with an explicit rebuttal mandate (tail risks,
        # overconcentration, thesis flaws), then CIO synthesizes a FINAL
        # decision that must address the challenge. This is the risk-veto
        # pattern from TradingAgents (portfolio manager can override the
        # trader), scoped to +2 bounded calls (no unbounded multi-round loop)
        # to keep cost predictable under the $30/week cap.
        draft_decision = decision
        try:
            risk_challenge_context = {
                "topic": topic,
                "draft_decision": str(draft_decision),
                "market_data": context_data.get("market_data"),
                "instruction": (
                    "Challenge this draft decision. You MUST identify at least one "
                    "concrete tail risk, overconcentration concern, or thesis flaw "
                    "if one exists — do not rubber-stamp. State APPROVE or VETO "
                    "explicitly with your reasoning. If VETO, state what must change."
                ),
            }
            risk_challenge = await self._call_agent_llm("Risk", risk_challenge_context, tier="fast")
            transcript.append(f"[Risk Challenge]: {risk_challenge}")

            final_synth_context = {
                **final_context,
                "draft_decision": str(draft_decision),
                "risk_challenge": str(risk_challenge),
                "instruction": (
                    "The Risk agent has challenged your draft decision above. "
                    "Produce your FINAL decision: either defend the draft with "
                    "reasoning that addresses the challenge, or revise the rating/"
                    "sizing to account for it. Do not ignore the challenge."
                ),
            }
            revised = await self._call_agent_llm("CIO", final_synth_context, tier=consensus_tier)
            if revised:
                decision = revised
        except Exception as e:
            logger.warning(f"Council: adversarial risk round failed (falling back to draft decision): {e}")

        # P3.2 (2026-07-11): independent grounding verification (informational only).
        grounding_note = await self._verify_grounding(str(decision), context_data.get("market_data"))

        self._archive_minutes(user_id, session_id, topic, str(decision), "\n".join(transcript))

        # Cold Processing Backup
        try:
            await self._write_cold_backup(user_id, session_id, topic, str(decision), str(grounding_note))
        except Exception as e:
            logger.warning(f"Cold Backup: failed to write: {e}")

        return {
            "session_id": session_id,
            "consensus": str(decision),
            "transcript": transcript,
            "grounding_check": grounding_note,
        }

    def _archive_minutes(self, user_id: str, session_id: str, topic: str, consensus: str, transcript: str) -> None:
        """
        Archive the session results to the vector repository for experience replay.
        將議程結果歸檔至向量儲存庫，以便進行復盤 (Experience Replay)。
        """
        try:
            # Real embedding of topic + consensus for semantic recall (768-dim,
            # nomic-embed-text). Falls back to a zero vector only if embedding is
            # unavailable, so archival never blocks. (2026-07-11: replaced the
            # permanent [0.0]*1536 placeholder that made semantic recall useless.)
            from src.infrastructure.llm.embedding_service import embed_text, EMBED_DIM
            embedding = embed_text(f"{topic}\n\n{consensus}") or ([0.0] * EMBED_DIM)
            self.vector_repo.add_council_minute(
                user_id=user_id,
                session_id=session_id,
                topic=topic,
                participants=["MapReduce_Council"],
                consensus=consensus,
                transcript=transcript,
                embedding=embedding
            )
        except Exception as e:
            logger.error(f"Failed to archive: {e}")

    async def _write_cold_backup(self, user_id: str, session_id: str, topic: str, consensus: str, verifier_note: str) -> None:
        """
        Local file-based cold storage backup of decision outcomes and grounding facts.
        """
        try:
            log_dir = "logs"
            os.makedirs(log_dir, exist_ok=True)
            log_file = os.path.join(log_dir, "workflow_cold_backup.jsonl")
            
            entry = {
                "timestamp": datetime.now().isoformat(),
                "user_id": user_id,
                "session_id": session_id,
                "topic": topic,
                "consensus": consensus,
                "verifier_note": verifier_note
            }
            
            def append_to_file():
                with open(log_file, "a", encoding="utf-8") as f:
                    f.write(json.dumps(entry, ensure_ascii=False) + "\n")
            
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, append_to_file)
            logger.info(f"Cold Processing Backup written successfully for session {session_id}")
        except Exception as e:
            logger.warning(f"Failed to write cold processing backup: {e}")
