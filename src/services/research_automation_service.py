"""
Research Automation Service — Phase 2
Automates weekly ticker research via LLM agents (Fundamental, Momentum, Sentiment),
stores structured results (confidence scores, thesis, risks) in ticker_research table,
and evaluates removal candidates.

Uses the same LLM pipeline as SentinelService (build_config_chain + ResilientLLMPipeline).
研究自動化服務 — Phase 2
每週透過 LLM Agent（基本面、動能、情緒）自動研究標的，
將結構化結果（信心指數、論點、風險）存入 ticker_research 表，
並評估剔除候選。
"""

import json
import asyncio
import logging
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict

from src.repositories.ticker_universe_repository import TickerUniverseRepository
from src.services.market_data_service import MarketDataService

logger = logging.getLogger(__name__)


@dataclass
class AgentResearchResult:
    """Structured output from an LLM agent research session."""
    confidence_score: float = 0.5          # 0.0–1.0
    expected_return: float = 0.05          # annual expected return
    risk_score: Optional[float] = None     # 0.0–1.0 (optional)
    thesis: str = ""                       # investment thesis summary
    risks: List[str] = field(default_factory=list)  # key risk factors
    target_weight: Optional[float] = None  # suggested allocation (optional)
    raw_response: str = ""                 # original LLM text (for audit)


class ResearchAutomationService:
    """
    Orchestrates LLM-driven research across all active tickers in the universe.
    Coordinates 3 agents per ticker: Fundamental (smart tier), Momentum (fast), Sentiment (fast).
    協調所有活躍標的的 LLM 研究：
    每標的 3 個 Agent：基本面（smart）、動能（fast）、情緒（fast）。
    """

    def __init__(self, user_id: str):
        self.user_id = user_id
        self.repo = TickerUniverseRepository()
        self.market = MarketDataService(user_id=user_id)
        self._pipeline = None  # lazy init

    # ── Public API ──

    async def run_weekly_research(
        self,
        max_tickers: int = 50,
        parallel: int = 3
    ) -> Dict[str, Any]:
        """
        Run full research cycle on all active tickers.
        Returns summary with counts and any errors.
        對所有活躍標的執行完整研究週期。
        """
        tickers = self.repo.get_all(self.user_id, status="active")
        if not tickers:
            return {"success": True, "total": 0, "message": "No active tickers to research"}

        results = []
        errors = []
        semaphore = asyncio.Semaphore(parallel)

        async def research_one(t: Dict[str, Any]) -> Optional[Dict[str, Any]]:
            async with semaphore:
                try:
                    return await self.run_ticker_research(t["ticker"])
                except Exception as e:
                    logger.error(f"Research failed for {t['ticker']}: {e}")
                    errors.append({"ticker": t["ticker"], "error": str(e)})
                    return None

        tasks = [research_one(t) for t in tickers]
        completed = await asyncio.gather(*tasks)

        for r in completed:
            if r:
                results.append(r)

        # Evaluate removals
        removals = await self.evaluate_removals()

        return {
            "success": True,
            "total": len(tickers),
            "researched": len(results),
            "errors": len(errors),
            "removal_candidates": removals.get("candidates", []),
            "detail": {
                "researched_tickers": [r["ticker"] for r in results],
                "error_details": errors[:5],
            },
        }

    async def run_ticker_research(self, ticker: str) -> Dict[str, Any]:
        """
        Run all 3 agents on one ticker and store aggregated result.
        對一個標的執行全部 3 個 Agent 並儲存聚合結果。
        """
        # Gather market context
        context = await self._build_ticker_context(ticker)

        # Call agents in parallel
        fundamental, momentum, sentiment = await asyncio.gather(
            self._call_agent("Fundamental", context, tier="smart"),
            self._call_agent("Momentum", context, tier="fast"),
            self._call_agent("Sentiment", context, tier="fast"),
        )

        # Aggregate scores (weighted: Fundamental 40%, Momentum 35%, Sentiment 25%)
        agg_confidence = (
            0.40 * fundamental.confidence_score
            + 0.35 * momentum.confidence_score
            + 0.25 * sentiment.confidence_score
        )
        agg_return = (
            0.40 * fundamental.expected_return
            + 0.35 * momentum.expected_return
            + 0.25 * sentiment.expected_return
        )
        all_risks = list(set(fundamental.risks + momentum.risks + sentiment.risks))

        # Pick best thesis (highest confidence agent's)
        agents = [(fundamental, "FundamentalAgent"), (momentum, "MomentumAgent"), (sentiment, "SentimentAgent")]
        best_agent = max(agents, key=lambda x: x[0].confidence_score)
        thesis = best_agent[0].thesis or f"Aggregated research for {ticker}"
        best_agent_name = best_agent[1]

        # Store in ticker_research (via repo)
        from datetime import timezone
        now = datetime.now(timezone.utc)

        success = self.repo.add_research(
            user_id=self.user_id,
            ticker=ticker,
            agent_name=best_agent_name,
            research_type="weekly_automated",
            confidence_score=round(agg_confidence, 4),
            target_weight=None,  # CIO determines target weight
            expected_return=round(agg_return, 4),
            risk_score=round(
                sum(a[0].risk_score or 0.5 for a in agents) / 3,
                4,
            ),
            thesis=thesis[:500],
            risks=all_risks[:10],
            data_sources={"agents": [a[1] for a in agents], "type": "weekly_llm_research"},
            raw_analysis={
                "fundamental": fundamental.raw_response[:1000],
                "momentum": momentum.raw_response[:1000],
                "sentiment": sentiment.raw_response[:1000],
            },
        )

        self.repo.add_log(
            user_id=self.user_id,
            ticker=ticker,
            action="research_updated",
            agent_name="ResearchAutomationService",
            reasoning=f"Aggregated confidence={agg_confidence:.2f}, return={agg_return:.2f}",
            old_status="",
            new_status="active",
        )

        return {
            "ticker": ticker,
            "confidence": round(agg_confidence, 4),
            "expected_return": round(agg_return, 4),
            "thesis": thesis[:100],
            "risk_count": len(all_risks),
            "best_agent": best_agent_name,
            "stored": success,
        }

    async def evaluate_removals(self) -> Dict[str, Any]:
        """
        Evaluate all active tickers for potential removal.
        Uses LLM to assess thesis degradation + simple rules (sustained negative momentum).
        評估所有活躍標的是否應剔除。
        """
        tickers = self.repo.get_all(self.user_id, status="active")
        if not tickers:
            return {"success": True, "candidates": []}

        candidates = []

        for t in tickers:
            ticker = t["ticker"]
            # Get recent research
            research = self.repo.get_research(self.user_id, ticker, limit=3)
            if not research:
                continue

            # Check if confidence has been declining
            confs = [float(r.get("confidence_score", 0.5)) for r in research]
            # 3-point decline check
            if len(confs) >= 3 and confs[-1] < confs[0] * 0.6:
                candidates.append({
                    "ticker": ticker,
                    "reason": "confidence_decline",
                    "detail": f"Confidence dropped from {confs[0]:.2f} to {confs[-1]:.2f}",
                    "confidence": confs[-1],
                })
                continue

            # Check latest confidence < 0.2
            latest_conf = confs[-1] if confs else 0.5
            if latest_conf < 0.2:
                candidates.append({
                    "ticker": ticker,
                    "reason": "low_confidence",
                    "detail": f"Confidence {latest_conf:.2f} < 0.2 threshold",
                    "confidence": latest_conf,
                })
                continue

            # Let LLM decide for borderline cases (confidence 0.2–0.35)
            if latest_conf < 0.35:
                context = await self._build_ticker_context(ticker)
                llm_result = await self._call_agent("Fundamental", context, tier="fast")
                removal_prompt = {
                    "ticker": ticker,
                    "current_confidence": latest_conf,
                    "thesis": research[0].get("thesis", ""),
                    "risks": research[0].get("risks", []),
                    "fundamental_conclusion": llm_result.thesis,
                    "question": "Should this ticker be removed from the universe? "
                                "Respond with JSON: {\"should_remove\": bool, \"reason\": str}"
                }
                try:
                    removal_raw = await self._call_llm_direct(
                                        "You are a portfolio analyst evaluating ticker retention. "
                                        "Respond ONLY with valid JSON.",
                                        json.dumps(removal_prompt),
                                        tier="fast",
                                    )
                    removal_data = json.loads(removal_raw)
                    if removal_data.get("should_remove"):
                        candidates.append({
                            "ticker": ticker,
                            "reason": "llm_recommended_removal",
                            "detail": removal_data.get("reason", "LLM recommendation"),
                            "confidence": latest_conf,
                        })
                except (json.JSONDecodeError, Exception) as e:
                    logger.debug(f"LLM removal eval failed for {ticker}: {e}")

        # Log removals
        for c in candidates:
            self.repo.add_log(
                user_id=self.user_id,
                ticker=c["ticker"],
                action="removal_candidate",
                agent_name="ResearchAutomationService",
                reasoning=f"{c['reason']}: {c['detail']}",
                old_status="active",
                new_status="removal_candidate",
            )

        return {"success": True, "candidates": candidates}

    # ── LLM Agent Calls ──

    async def _call_agent(
        self, agent_name: str, context: Dict[str, Any], tier: str = "smart"
    ) -> AgentResearchResult:
        """Call a single LLM agent for research and parse structured output."""
        agent_prompts = {
            "Fundamental": (
                "You are a Fundamental analyst. Analyze the ticker's financial statements, "
                "valuation, and competitive position. "
                "Respond with JSON ONLY:\n"
                "{\n"
                '  "confidence_score": 0.0-1.0 (how confident are you in this ticker?), \n'
                '  "expected_return": 0.0-1.0 (annual expected return, e.g. 0.12 = 12%), \n'
                '  "risk_score": 0.0-1.0 (overall risk, 0=low risk), \n'
                '  "thesis": "concise investment thesis (max 200 chars)", \n'
                '  "risks": ["risk1", "risk2", "risk3"]\n'
                "}"
            ),
            "Momentum": (
                "You are a Momentum analyst. Analyze price trends, technical indicators, "
                "and volume patterns. "
                "Respond with JSON ONLY:\n"
                "{\n"
                '  "confidence_score": 0.0-1.0, \n'
                '  "expected_return": 0.0-1.0, \n'
                '  "risk_score": 0.0-1.0, \n'
                '  "thesis": "momentum thesis (max 200 chars)", \n'
                '  "risks": ["risk1", "risk2"]\n'
                "}"
            ),
            "Sentiment": (
                "You are a Sentiment analyst. Analyze news sentiment, social media trends, "
                "and market sentiment indicators. "
                "Respond with JSON ONLY:\n"
                "{\n"
                '  "confidence_score": 0.0-1.0, \n'
                '  "expected_return": 0.0-1.0, \n'
                '  "risk_score": 0.0-1.0, \n'
                '  "thesis": "sentiment thesis (max 200 chars)", \n'
                '  "risks": ["risk1", "risk2"]\n'
                "}"
            ),
        }

        system_prompt = agent_prompts.get(agent_name, agent_prompts["Fundamental"])
        user_prompt = json.dumps(context, indent=2, default=str)

        try:
            raw = await self._call_llm_direct(system_prompt, user_prompt, tier)
            parsed = self._parse_agent_response(raw)
            parsed.raw_response = raw[:2000]
            return parsed
        except Exception as e:
            logger.warning(f"Agent {agent_name} failed for {context.get('ticker','?')}: {e}")
            result = AgentResearchResult()
            result.raw_response = f"Error: {e}"
            return result

    async def _call_llm_direct(
        self, system_prompt: str, user_prompt: str, tier: str = "smart"
    ) -> str:
        """Direct LLM call via ResilientLLMPipeline (same as SentinelService)."""
        from src.infrastructure.llm.llm_config_chain import build_config_chain
        from src.infrastructure.llm.resilient_pipeline import ResilientLLMPipeline

        chain = build_config_chain(self.user_id, tier)
        if not chain:
            return json.dumps({"error": f"No model configured for tier={tier}"})

        pipeline = ResilientLLMPipeline(config_chain=chain)
        from src.domain.interfaces import Message

        messages = [
            Message(role="system", content=system_prompt),
            Message(role="user", content=user_prompt),
        ]

        response, _ = await pipeline.execute(messages, temperature=0.3, max_tokens=2000)
        return response if isinstance(response, str) else str(response)

    def _parse_agent_response(self, raw: str) -> AgentResearchResult:
        """Parse LLM response into structured AgentResearchResult."""
        result = AgentResearchResult()

        # Try to extract JSON from response
        data = self._extract_json(raw)
        if not data:
            return result

        result.confidence_score = float(data.get("confidence_score", 0.5))
        result.expected_return = float(data.get("expected_return", 0.05))
        result.risk_score = float(data["risk_score"]) if data.get("risk_score") is not None else None
        result.thesis = str(data.get("thesis", ""))[:500]
        result.risks = data.get("risks", [])[:10]
        if isinstance(result.risks, list):
            result.risks = [str(r) for r in result.risks]

        # Clamp
        result.confidence_score = max(0.0, min(1.0, result.confidence_score))
        result.expected_return = max(-0.5, min(1.0, result.expected_return))
        if result.risk_score is not None:
            result.risk_score = max(0.0, min(1.0, result.risk_score))

        return result

    @staticmethod
    def _extract_json(text: str) -> Optional[Dict[str, Any]]:
        """Extract first JSON object from text, tolerating markdown code fences."""
        # Try direct parse
        text = text.strip()
        if text.startswith("{"):
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                pass

        # Try extracting from ```json ... ``` block
        import re
        match = re.search(r"```(?:json)?\s*\n?(\{.*?\})\s*\n?```", text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(1))
            except json.JSONDecodeError:
                pass

        # Try finding first { ... } at any depth (crude)
        brace_start = text.find("{")
        brace_end = text.rfind("}")
        if brace_start >= 0 and brace_end > brace_start:
            try:
                return json.loads(text[brace_start : brace_end + 1])
            except json.JSONDecodeError:
                pass

        return None

    # ── Context Building ──

    async def _build_ticker_context(self, ticker: str) -> Dict[str, Any]:
        """Gather all market data for a ticker into a context dict for LLM agents."""
        try:
            price_task = asyncio.create_task(
                asyncio.to_thread(self.market.get_ohlcv, ticker, 90)
            )
            financials_task = asyncio.to_thread(self.market.get_financials, ticker)
            news_task = asyncio.to_thread(self.market.get_news, ticker)
            indicators_task = asyncio.to_thread(self.market.get_technical_indicators, ticker)

            price_data, financials, news, indicators = await asyncio.gather(
                price_task, financials_task, news_task, indicators_task,
                return_exceptions=True,
            )

            context = {
                "ticker": ticker,
                "analysis_date": datetime.now(timezone.utc).isoformat(),
                "price_data": self._summarize_prices(price_data) if not isinstance(price_data, Exception) else {},
                "financials": self._summarize_financials(financials) if not isinstance(financials, Exception) else {},
                "news_summary": self._summarize_news(news) if not isinstance(news, Exception) else [],
                "indicators": indicators if not isinstance(indicators, Exception) else {},
            }

            return context
        except Exception as e:
            logger.error(f"Context building failed for {ticker}: {e}")
            return {"ticker": ticker, "error": str(e)}

    def _summarize_prices(self, ohlcv_data) -> Dict[str, Any]:
        """Extract key price stats from OHLCV data."""
        if not ohlcv_data or not isinstance(ohlcv_data, dict):
            return {}
        close = ohlcv_data.get("close", [])
        if not close:
            return {}
        prices = [float(c) for c in close if c]
        if not prices:
            return {}
        return {
            "current_price": round(prices[-1], 2),
            "high_90d": round(max(prices), 2),
            "low_90d": round(min(prices), 2),
            "avg_90d": round(sum(prices) / len(prices), 2),
            "price_change_90d_pct": round((prices[-1] - prices[0]) / prices[0] * 100, 2) if len(prices) > 1 else 0,
            "volatility_90d": round((max(prices) - min(prices)) / min(prices) * 100, 2) if min(prices) > 0 else 0,
        }

    def _summarize_financials(self, financials) -> Dict[str, Any]:
        """Extract key fundamental metrics."""
        if not financials or not isinstance(financials, dict):
            return {}
        keys_of_interest = [
            "market_cap", "trailing_pe", "forward_pe", "price_to_book",
            "dividend_yield", "revenue_growth", "profit_margins",
            "return_on_equity", "debt_to_equity", "current_ratio",
            "sector", "industry", "short_ratio", "beta",
        ]
        return {k: financials.get(k) for k in keys_of_interest if k in financials}

    def _summarize_news(self, news) -> List[Dict[str, Any]]:
        """Extract recent news headlines."""
        if not news or not isinstance(news, list):
            return []
        summaries = []
        for n in news[:5]:
            summaries.append({
                "title": n.get("title", "")[:100],
                "date": str(n.get("date", "")),
                "summary": n.get("summary", "")[:200],
            })
        return summaries