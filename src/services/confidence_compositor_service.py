"""
Confidence Compositor Service — Phase 4 (Agent-Integrated)

Aggregates multi-agent confidence scores into composite investment decisions
via direct structured LLM scoring calls for each agent category.

Architecture:
  1. Sentinel detects excess cash → triggers Compositor
  2. Compositor sends structured scoring prompts to LLM per agent × ticker
  3. Each prompt asks for: score (0-10), key factors, rationale
  4. Weighted ensemble: Fundamental 35%, Momentum 25%, Sentiment 20%, Risk 20%
  5. Proportional betting: allocation % = composite_score / sum(all_scores)
  6. Cash reservation: higher confidence = deploy more, low = keep cash
"""

import json
import logging
import hashlib
from typing import Dict, List, Any, Optional, Tuple
from src.domain.interfaces import Message
from dataclasses import dataclass
from datetime import datetime

logger = logging.getLogger("ConfidenceCompositorService")


@dataclass
class AgentSubScore:
    """Sub-score from a single agent."""
    agent_name: str
    ticker: str
    confidence: float  # 0-10 scale
    factors: Dict[str, Any]
    rationale: str
    timestamp: str


class CompositorService:
    """
    Aggregates multi-agent confidence scores into composite decisions
    using real LLM calls with structured output per agent category.

    Implements:
      - Per-agent × per-ticker structured scoring via LLM
      - Weighted ensemble (confidence-weighted averaging)
      - Cash-reservation logic (don't force deploy if uncertainty too high)
      - Proportional betting (Kelly criterion adjacent)
    """

    # Agent → tier mapping (matches agent factory defaults)
    AGENT_TIERS = {
        "Fundamental": "smart",
        "Momentum": "fast",
        "Sentiment": "fast",
        "Risk": "fast",
    }

    def __init__(self, user_id: str):
        self.user_id = user_id
        self.min_threshold = 5.0  # 5/10 minimum to execute
        self.max_single_allocation = 0.25  # 25% of excess cash max
        self.min_allocation = 0.05  # 5% minimum allocation

        # Agent weights (can be dynamic based on historical accuracy)
        self.agent_weights = {
            "fundamental": 0.35,
            "momentum": 0.25,
            "sentiment": 0.20,
            "risk": 0.20,
        }

        # Lazy-init LLM router & pipeline cache
        self._router = None
        self._pipelines = {}  # tier -> ResilientLLMPipeline

    # ── LLM Infrastructure ──

    async def _get_pipeline(self, tier: str) -> Any:
        """Lazy-initialize a ResilientLLMPipeline for the given tier."""
        if tier in self._pipelines:
            return self._pipelines[tier]

        from src.services.settings_service import SettingsService
        from src.services.token_logger_service import TokenLoggerService
        from src.infrastructure.llm.budget_aware_model_router import BudgetAwareModelRouter

        if not self._router:
            settings_svc = SettingsService(user_id=self.user_id)
            token_logger = TokenLoggerService()
            self._router = BudgetAwareModelRouter(settings_svc, token_logger)

        pipeline = self._router.get_resilient_gateway(
            user_id=self.user_id,
            tier=tier,
        )
        self._pipelines[tier] = pipeline
        return pipeline

    async def _score_via_llm(
        self,
        ticker: str,
        agent_name: str,
        prompt_template: str,
        tier: str,
    ) -> Tuple[float, Dict[str, Any]]:
        """Send a structured scoring prompt to LLM and parse the JSON response."""
        try:
            pipeline = await self._get_pipeline(tier)
            prompt = prompt_template.format(ticker=ticker)

            response, attempts = await pipeline.execute([
                Message(role="system", content="You are an expert investment analyst. Return ONLY valid JSON."),
                Message(role="user", content=prompt),
            ])

            # Extract JSON from response
            cleaned = response.strip()
            if "```json" in cleaned:
                cleaned = cleaned.split("```json")[1].split("```")[0]
            elif "```" in cleaned:
                cleaned = cleaned.split("```")[1].split("```")[0]

            # Find first { to last }
            start = cleaned.find("{")
            end = cleaned.rfind("}")
            if start != -1 and end != -1:
                cleaned = cleaned[start:end + 1]

            data = json.loads(cleaned)
            raw_score = data.get("score")
            if raw_score is None:
                logger.warning(f"LLM returned null score for {agent_name}/{ticker}, response keys: {list(data.keys())}")
                raw_score = 5.0
            score = float(raw_score)
            score = max(0.0, min(10.0, score))  # Clamp 0-10

            factors = {
                "key_factor": data.get("key_factor", "N/A"),
                "details": data.get("details", ""),
                "rationale": data.get("rationale", ""),
            }
            # Include any extra fields from the response
            for k, v in data.items():
                if k not in ("score", "key_factor", "details", "rationale"):
                    factors[k] = v

            return round(score, 1), factors

        except (json.JSONDecodeError, ValueError, TypeError) as e:
            logger.warning(f"LLM scoring parse error for {agent_name}/{ticker}: {e}. Raw: {response[:200]}...")
            fallback_score, fallback_factors = self._fallback_score(ticker, agent_name)
            fallback_factors["_fallback_reason"] = str(e)
            return fallback_score, fallback_factors
        except Exception as e:
            logger.warning(f"LLM scoring failed for {agent_name}/{ticker}: {e}")
            fallback_score, fallback_factors = self._fallback_score(ticker, agent_name)
            fallback_factors["_fallback_reason"] = str(e)
            return fallback_score, fallback_factors

    def _fallback_score(self, ticker: str, agent_name: str) -> Tuple[float, Dict[str, Any]]:
        """Deterministic hash-based fallback when LLM is unavailable."""
        seed = self._ticker_hash(ticker + "_" + agent_name.lower())

        base_map = {
            "fundamental": 7.0 + (seed % 5) * 0.5,
            "momentum": 5.0 + (seed % 5) * 0.8,
            "sentiment": 6.0 + (seed % 4) * 0.7,
            "risk": 5.0 + (seed % 5) * 0.6,
        }
        base = base_map.get(agent_name.lower(), 6.0)
        return min(10.0, base), {
            "key_factor": "Fallback (hash-based)",
            "details": f"LLM unavailable, used deterministic seed {seed}",
            "rationale": f"{agent_name} evaluated (fallback mode)",
        }

    # ── Agent Scoring Prompts ──

    _FUNDAMENTAL_PROMPT = """Analyze {ticker} fundamentals and return a confidence score (0-10).

Consider: EPS growth trends, profit margins, revenue growth, P/E ratio, debt levels,
supply chain dynamics, competitive moat, and management quality.

Return JSON:
{{
  "score": <float 0-10>,
  "key_factor": "<single most important fundamental factor>",
  "details": "<brief explanation>",
  "rationale": "<one-sentence rationale>",
  "eps_growth": "<observed or estimated EPS growth %>",
  "pe_ratio": "<P/E ratio estimate>",
  "margin": "<profit margin estimate %>"
}}"""

    _MOMENTUM_PROMPT = """Analyze {ticker} price momentum and return a confidence score (0-10).

Consider: RSI, moving averages (20/50/200), MACD, volume trends, recent price action,
support/resistance levels, and relative strength vs sector.

Return JSON:
{{
  "score": <float 0-10>,
  "key_factor": "<single most important momentum factor>",
  "details": "<brief explanation>",
  "rationale": "<one-sentence rationale>",
  "rsi": "<RSI value estimate>",
  "sma_20": "<20-day SMA change estimate %>",
  "volume": "<volume trend description>"
}}"""

    _SENTIMENT_PROMPT = """Analyze {ticker} market sentiment and return a confidence score (0-10).

Consider: Recent news headlines, social media sentiment (Reddit, Twitter/X),
analyst ratings changes, insider trading activity, institutional flows,
and short interest data.

Return JSON:
{{
  "score": <float 0-10>,
  "key_factor": "<single most important sentiment factor>",
  "details": "<brief explanation>",
  "rationale": "<one-sentence rationale>",
  "news_sentiment": "<overall news sentiment: bullish/neutral/bearish>",
  "insider_activity": "<insider buying/selling activity>",
  "overall_tone": "<brief market tone>"
}}"""

    _RISK_PROMPT = """Analyze {ticker} risk profile and return a confidence score (0-10);
a HIGH score means LOW risk (safer investment).

Consider: Beta (volatility vs market), drawdown risk, market cap stability,
liquidity (trading volume), sector concentration risk, geopolitical exposure,
and correlation with broader market indices.

Return JSON:
{{
  "score": <float 0-10, HIGH=low risk>,
  "key_factor": "<single most important risk factor>",
  "details": "<brief explanation>",
  "rationale": "<one-sentence rationale>",
  "beta": "<beta estimate>",
  "volatility": "<volatility description>",
  "liquidity": "<liquidity assessment>"
}}"""

    # ── Main Public API ──

    async def compute_composite_decision(
        self,
        candidates: List[Dict[str, Any]],
        excess_cash: float,
        cash_ratio: float,
        target_cash_ratio: float,
    ) -> List[Dict[str, Any]]:
        """
        Compute composite decisions for all candidates.

        Two-pass approach:
          1. Gather all agent sub-scores for every ticker (parallel per-ticker)
          2. Compute proportional allocations based on actual score sums
        """
        sub_score_map = {}  # ticker -> {scores, composite, should_execute, reserve, candidate}

        # ── Pass 1: Gather all agent scores ──
        for candidate in candidates:
            ticker = candidate.get("ticker")
            if not ticker:
                continue

            sub_scores = await self._gather_agent_scores(ticker, cash_ratio, target_cash_ratio)
            composite_score, should_execute = self._aggregate_scores(sub_scores)
            cash_reserve = self._compute_cash_reserve_factor(composite_score, cash_ratio)
            sub_score_map[ticker] = {
                "scores": sub_scores,
                "composite": composite_score,
                "should_execute": should_execute,
                "reserve": cash_reserve,
                "candidate": candidate,
            }

        # ── Pass 2: Compute proportional allocations ──
        total_composite = sum(
            v["composite"] for v in sub_score_map.values()
        )

        decisions = []
        for ticker, data in sub_score_map.items():
            alloc_pct = self._compute_allocation_pct(
                composite_score=data["composite"],
                excess_cash=excess_cash,
                cash_reserve_factor=data["reserve"],
                total_composite_score=total_composite,
            )

            decision = self._build_decision(
                ticker=ticker,
                candidate=data["candidate"],
                sub_scores=data["scores"],
                composite_score=data["composite"],
                allocation_pct=alloc_pct,
                should_execute=data["should_execute"],
                cash_reserve_recommendation=data["reserve"],
                excess_cash=excess_cash,
            )
            decisions.append(decision)

        # Normalize to not exceed total excess cash
        decisions = self._normalize_allocations(decisions, excess_cash)

        return decisions

    async def _gather_agent_scores(
        self,
        ticker: str,
        cash_ratio: float,
        target_cash_ratio: float,
    ) -> List[AgentSubScore]:
        """Query each agent (via LLM scoring) for their sub-score and factors."""
        sub_scores = []

        agent_configs = [
            ("Fundamental", self._query_fundamental_agent(ticker)),
            ("Momentum", self._query_momentum_agent(ticker)),
            ("Sentiment", self._query_sentiment_agent(ticker)),
            ("Risk", self._query_risk_agent(ticker, cash_ratio)),
        ]

        for agent_name, coro in agent_configs:
            try:
                score, factors = await coro
            except Exception as error:
                logger.warning(f"{agent_name} Agent failed for {ticker}: {error}")
                score, factors = 5.0, {"error": str(error), "key_factor": "Agent unavailable"}
            sub_scores.append(AgentSubScore(
                agent_name=agent_name,
                ticker=ticker,
                confidence=score,
                factors=factors,
                rationale=factors.get("rationale", ""),
                timestamp=datetime.now().isoformat(),
            ))

        return sub_scores

    # ── Per-Agent Query Methods ──

    async def _query_fundamental_agent(self, ticker: str) -> Tuple[float, Dict[str, Any]]:
        """Score fundamentals via LLM (smart tier)."""
        return await self._score_via_llm(
            ticker, "Fundamental",
            self._FUNDAMENTAL_PROMPT,
            tier=self.AGENT_TIERS["Fundamental"],
        )

    async def _query_momentum_agent(self, ticker: str) -> Tuple[float, Dict[str, Any]]:
        """Score momentum via LLM (fast tier)."""
        return await self._score_via_llm(
            ticker, "Momentum",
            self._MOMENTUM_PROMPT,
            tier=self.AGENT_TIERS["Momentum"],
        )

    async def _query_sentiment_agent(self, ticker: str) -> Tuple[float, Dict[str, Any]]:
        """Score sentiment via LLM (fast tier)."""
        return await self._score_via_llm(
            ticker, "Sentiment",
            self._SENTIMENT_PROMPT,
            tier=self.AGENT_TIERS["Sentiment"],
        )

    async def _query_risk_agent(
        self,
        ticker: str,
        cash_ratio: float,
    ) -> Tuple[float, Dict[str, Any]]:
        """Score risk via LLM (fast tier) — high score = low risk."""
        prompt = self._RISK_PROMPT.format(ticker=ticker, cash_ratio=cash_ratio)
        try:
            pipeline = await self._get_pipeline(self.AGENT_TIERS["Risk"])

            response, attempts = await pipeline.execute([
                Message(role="system", content="You are a risk assessment expert. Return ONLY valid JSON."),
                Message(role="user", content=prompt),
            ])

            # Extract JSON
            cleaned = response.strip()
            if "```json" in cleaned:
                cleaned = cleaned.split("```json")[1].split("```")[0]
            elif "```" in cleaned:
                cleaned = cleaned.split("```")[1].split("```")[0]

            start = cleaned.find("{")
            end = cleaned.rfind("}")
            if start != -1 and end != -1:
                cleaned = cleaned[start:end + 1]

            data = json.loads(cleaned)
            score = float(data.get("score", 5.0))
            score = max(0.0, min(10.0, score))

            # Adjust for cash ratio: higher cash = buffer against risk = bump score
            cash_bonus = min(1.0, max(0, (cash_ratio - 0.20)) * 2.0)
            score = min(10.0, score + cash_bonus)

            factors = {
                "key_factor": data.get("key_factor", "N/A"),
                "details": data.get("details", ""),
                "rationale": data.get("rationale", ""),
                "beta": data.get("beta", "N/A"),
                "volatility": data.get("volatility", "N/A"),
                "liquidity": data.get("liquidity", "N/A"),
                "cash_ratio_adjustment": round(cash_bonus, 2),
            }

            return round(score, 1), factors

        except Exception as e:
            logger.warning(f"Risk LLM scoring failed for {ticker}: {e}")
            return self._fallback_score(ticker, "risk")

    # ── Score Aggregation ──

    def _aggregate_scores(self, sub_scores: List[AgentSubScore]) -> Tuple[float, bool]:
        """Compute weighted average of sub-scores. Returns (composite_score, should_execute)."""
        if not sub_scores:
            return 5.0, False

        weighted_sum = 0.0
        total_weight = 0.0

        for score in sub_scores:
            weight = self.agent_weights.get(score.agent_name.lower(), 0.25)
            weighted_sum += score.confidence * weight
            total_weight += weight

        composite = weighted_sum / total_weight if total_weight > 0 else 5.0
        should_execute = composite >= self.min_threshold

        return composite, should_execute

    def _compute_cash_reserve_factor(
        self,
        composite_score: float,
        cash_ratio: float,
    ) -> float:
        """
        Compute how much cash to retain based on confidence.

        - High confidence (8+): keep 20% reserve, deploy 80%
        - Medium-high (6-8): keep 30-40%
        - Medium (5-6): keep 40-80%
        - Low (<5): keep 80-95%
        """
        if composite_score >= 8.0:
            reserve = 0.20
        elif composite_score >= 6.0:
            reserve = 0.30 + (8.0 - composite_score) * 0.05
        elif composite_score >= 5.0:
            reserve = 0.40 + (6.0 - composite_score) * 0.40
        else:
            reserve = 0.80 + (5.0 - composite_score) * 0.03

        return max(0.10, min(0.95, round(reserve, 2)))

    def _compute_allocation_pct(
        self,
        composite_score: float,
        excess_cash: float,
        cash_reserve_factor: float,
        total_composite_score: float,
    ) -> float:
        """
        Compute proportional allocation as fraction of excess_cash.

        allocation_pct = (score / total_score) × (1 - reserve)
        """
        if total_composite_score <= 0 or excess_cash <= 0:
            return 0.0

        deployable_share = composite_score / total_composite_score
        raw_pct = deployable_share * (1 - cash_reserve_factor)

        return max(self.min_allocation, min(self.max_single_allocation, raw_pct))

    def _build_decision(
        self,
        ticker: str,
        candidate: Dict[str, Any],
        sub_scores: List[AgentSubScore],
        composite_score: float,
        allocation_pct: float,
        should_execute: bool,
        cash_reserve_recommendation: float,
        excess_cash: float,
    ) -> Dict[str, Any]:
        """Build the final decision dictionary with Sentinel-compatible keys."""
        alloc_amount = round(excess_cash * allocation_pct, 2) if should_execute else 0.0

        return {
            "ticker": ticker,
            "candidate": candidate,
            "composite_score": round(composite_score, 2),
            "allocation_pct": round(allocation_pct, 4),
            "allocation_amount": alloc_amount,
            "should_execute": should_execute,
            "cash_reserve_pct": round(cash_reserve_recommendation, 2),
            "breakdown": [
                {
                    "agent": s.agent_name,
                    "confidence": s.confidence,
                    "key_factor": s.factors.get("key_factor", "N/A"),
                    "factors": s.factors,
                }
                for s in sub_scores
            ],
            "rationale": self._build_rationale(sub_scores, composite_score),
        }

    def _normalize_allocations(
        self,
        decisions: List[Dict[str, Any]],
        total_excess_cash: float,
    ) -> List[Dict[str, Any]]:
        """Normalize allocations to ensure total doesn't exceed excess_cash."""
        executables = [d for d in decisions if d["should_execute"]]
        if not executables:
            return decisions

        total_pct = sum(d["allocation_pct"] for d in executables)

        # Scale down if total > 1.0
        if total_pct > 1.0:
            scale = 1.0 / total_pct
            for d in executables:
                d["allocation_pct"] = round(d["allocation_pct"] * scale, 4)
                d["allocation_amount"] = round(d["allocation_pct"] * total_excess_cash, 2)

        # Re-compute amounts for all
        for d in decisions:
            if d["should_execute"]:
                d["allocation_amount"] = round(d["allocation_pct"] * total_excess_cash, 2)

        return decisions

    def _build_rationale(
        self,
        sub_scores: List[AgentSubScore],
        composite_score: float,
    ) -> str:
        """Build human-readable rationale from sub-scores."""
        lines = [f"Composite confidence: {composite_score:.1f}/10"]
        for s in sub_scores:
            rationale = s.factors.get("rationale", s.factors.get("key_factor", "N/A"))
            lines.append(f"  ├─ {s.agent_name}: {s.confidence:.1f}/10 ({rationale})")
        return "\n".join(lines)

    def _ticker_hash(self, ticker: str) -> int:
        """Deterministic hash per ticker for reproducible fallback scores."""
        return int(hashlib.md5(ticker.encode()).hexdigest()[:8], 16)
