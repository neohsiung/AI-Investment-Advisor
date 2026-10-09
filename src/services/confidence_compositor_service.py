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

import asyncio
import json
import logging
import hashlib
import math
import re
from typing import Dict, List, Any, Optional, Tuple
from src.domain.interfaces import Message
from dataclasses import dataclass
from datetime import datetime
from src.config.owner import resolve_user_id

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


def _clean_trailing_commas(json_str: str) -> str:
    """Remove trailing commas before closing braces/brackets (common LLM glitch)."""
    return re.sub(r",\s*([\]}])", r"\1", json_str)


def _try_parse_score_dict(blob: str) -> Optional[Dict[str, Any]]:
    """Attempt to parse a JSON dict and ensure it contains a valid float 'score'."""
    if not blob or not blob.strip():
        return None
    obj = None
    try:
        obj = json.loads(blob)
    except (ValueError, TypeError):
        try:
            obj = json.loads(_clean_trailing_commas(blob))
        except (ValueError, TypeError):
            return None

    if not isinstance(obj, dict):
        return None
    raw = obj.get("score")
    if raw is None:
        return None
    try:
        float(raw)
        return obj
    except (TypeError, ValueError):
        # Skips echoed template where score is literal "<float 0-10>"
        return None


def _extract_score_object(text: str) -> Dict[str, Any]:
    """
    Pull the scoring object out of an LLM reply that may contain reasoning or prose.
    從可能夾雜思考過程或自然語言的 LLM 回覆中取出評分物件。

    Scans:
      1. Strips <think>...</think> reasoning tags
      2. Markdown code blocks ```(?:json)? {...} ``` (scanned from LAST to FIRST)
      3. Balanced {...} regions (scanned from LAST to FIRST)
      4. Innermost {"score": ...} regex fallback
    """
    if not text:
        raise json.JSONDecodeError("empty response", "", 0)

    # 1. Strip <think>...</think> reasoning tags
    cleaned = re.sub(r"(?is)<think>.*?</think>", "", text).strip()

    # 2. Check for markdown code blocks (scan from LAST to FIRST, since final answers follow reasoning)
    code_blocks = re.findall(r"(?is)```(?:json)?\s*(\{.*?\})\s*```", cleaned)
    for block in reversed(code_blocks):
        obj = _try_parse_score_dict(block.strip())
        if obj is not None:
            return obj

    # 3. Scan all balanced {...} regions from LAST to FIRST
    candidates = []
    depth = 0
    start = -1
    for i, ch in enumerate(cleaned):
        if ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}":
            if depth > 0:
                depth -= 1
                if depth == 0 and start != -1:
                    candidates.append(cleaned[start:i + 1])
                    start = -1

    for blob in reversed(candidates):
        obj = _try_parse_score_dict(blob)
        if obj is not None:
            return obj

    # 4. Fallback: regex search for any innermost {"score": ...} object
    match = re.search(r"\{[^{}]*\"score\"[^{}]*\}", cleaned)
    if match:
        obj = _try_parse_score_dict(match.group(0))
        if obj is not None:
            return obj

    # Preserve standard failure behavior for caller's except clause
    raise json.JSONDecodeError("no scoring object found in response", text[:200], 0)


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
        self.user_id = resolve_user_id(user_id)
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
        response = ""
        try:
            pipeline = await self._get_pipeline(tier)
            prompt = prompt_template.format(ticker=ticker)

            response, attempts = await pipeline.execute([
                Message(role="system", content="You are an expert investment analyst. Return ONLY valid JSON."),
                Message(role="user", content=prompt),
            ])

            # Extract JSON from response via resilient extractor
            data = _extract_score_object(response)
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
        sub_scores: List[AgentSubScore] = []

        async def _safe_query(agent_name: str, coro_func) -> Tuple[str, float, Dict[str, Any]]:
            try:
                score, factors = await coro_func()
            except Exception as error:
                logger.warning(f"{agent_name} Agent failed for {ticker}: {error}")
                score, factors = 5.0, {"error": str(error), "key_factor": "Agent unavailable"}
            return agent_name, score, factors

        agent_tasks = [
            _safe_query("Fundamental", lambda: self._query_fundamental_agent(ticker)),
            _safe_query("Momentum", lambda: self._query_momentum_agent(ticker)),
            _safe_query("Sentiment", lambda: self._query_sentiment_agent(ticker)),
            _safe_query("Risk", lambda: self._query_risk_agent(ticker, cash_ratio)),
        ]

        results = await asyncio.gather(*agent_tasks)

        for agent_name, score, factors in results:
            sub_scores.append(AgentSubScore(
                agent_name=agent_name,
                ticker=ticker,
                confidence=score,
                factors=factors,
                rationale=factors.get("rationale", ""),
                timestamp=datetime.now().isoformat(),
            ))

        # Query and evaluate active synthesized factors
        synth_sub_scores = await self._gather_synthesized_factor_scores(ticker)
        sub_scores.extend(synth_sub_scores)

        # Query active micro event bias (個經事件偏置)
        try:
            from src.services.event_impact_service import EventImpactService
            impact_svc = EventImpactService(user_id=self.user_id)
            micro_bias, active_events = impact_svc.get_ticker_micro_bias(ticker)
            if active_events and micro_bias != 0.0:
                latest_evt = active_events[0]
                sub_scores.append(AgentSubScore(
                    agent_name="Event_Bias",
                    ticker=ticker,
                    confidence=max(0.0, min(10.0, 5.0 + micro_bias * 2.5)),
                    factors={
                        "key_factor": f"Event Bias ({micro_bias:+.2f} pt)",
                        "headline": latest_evt.get("headline", ""),
                        "current_impact": micro_bias,
                        "category": latest_evt.get("category", "event"),
                        "active_events_count": len(active_events),
                        "remaining_hours": latest_evt.get("remaining_hours", 0.0),
                    },
                    rationale=f"Active micro event bias for {ticker}: {latest_evt.get('headline', '')} (Impact: {micro_bias:+.2f} pt)",
                    timestamp=datetime.now().isoformat(),
                ))
        except Exception as e:
            logger.warning(f"Failed to gather micro event bias for {ticker}: {e}")

        return sub_scores

    async def _gather_synthesized_factor_scores(self, ticker: str) -> List[AgentSubScore]:
        """
        Evaluate all ACTIVE synthesized factor code artifacts against recent market data for `ticker`.
        Returns a list of AgentSubScore objects for active synthesized factors.
        """
        sub_scores = []
        try:
            from src.services.canary_shadow_runner import canary_runner, ArtifactStatus
            active_artifacts = canary_runner.list_artifacts(
                user_id=self.user_id,
                status=ArtifactStatus.ACTIVE,
            )
            if not active_artifacts:
                return sub_scores

            # Fetch recent market data for ticker
            market_df = None
            try:
                from src.data.providers.yfinance_provider import YFinanceProvider
                yf_provider = YFinanceProvider()
                market_df = yf_provider.fetch_history(ticker, period="60d")
            except Exception as e:
                logger.warning("Could not fetch market data from YFinanceProvider for %s: %s", ticker, e)

            # Fallback data generation if market data is unavailable (e.g. offline/mock environment)
            if market_df is None or market_df.empty:
                import numpy as np
                import pandas as pd
                n = 40
                dates = pd.date_range(end=datetime.now(), periods=n, freq="D")
                seed = self._ticker_hash(ticker)
                np.random.seed(seed % 10000)
                close = 100.0 + np.cumsum(np.random.normal(0.1, 1.0, n))
                market_df = pd.DataFrame({
                    "Open": close - 0.5,
                    "High": close + 1.0,
                    "Low": close - 1.0,
                    "Close": close,
                    "Volume": np.random.randint(1000, 20000, n),
                }, index=dates)

            for art in active_artifacts:
                try:
                    local_ns = {}
                    exec(art.source_code, local_ns)  # nosec B102
                    factor_func = local_ns.get("calculate_factor")
                    if not factor_func:
                        logger.warning("Artifact %s missing calculate_factor function", art.name)
                        continue

                    # Execute factor calculation
                    factor_series = factor_func(market_df, art.parameters)
                    if factor_series is None or len(factor_series) == 0:
                        logger.warning("Artifact %s returned empty factor series for %s", art.name, ticker)
                        continue

                    valid_vals = factor_series.dropna()
                    if valid_vals.empty:
                        raw_val = 0.0
                    else:
                        raw_val = float(valid_vals.iloc[-1])

                    # Standardize raw factor to 0.0-10.0 scale using bounded sigmoid normalization
                    norm_score = 10.0 / (1.0 + math.exp(-max(-5.0, min(5.0, raw_val))))
                    confidence = round(max(0.0, min(10.0, norm_score)), 1)
                    eff_weight_cap = canary_runner.get_effective_weight_cap(art)

                    sub_scores.append(AgentSubScore(
                        agent_name=f"Synth_{art.name}",
                        ticker=ticker,
                        confidence=confidence,
                        factors={
                            "key_factor": f"Regime: {art.parameters.get('target_regime', 'QUANT_FACTOR')}",
                            "raw_factor_value": round(raw_val, 4),
                            "target_regime": art.parameters.get("target_regime"),
                            "artifact_id": art.id,
                            "source": "autonomous_synthesis",
                            "weight_cap": eff_weight_cap,
                            "approval_type": art.parameters.get("approval_type", "manual"),
                        },
                        rationale=f"Active synthesized factor {art.name} evaluated on {ticker} (value={raw_val:.4f}, weight_cap={eff_weight_cap:.2f})",
                        timestamp=datetime.now().isoformat(),
                    ))
                except Exception as e:
                    logger.warning("Failed to evaluate synthesized factor %s for %s: %s", art.name, ticker, e)
                    # Constraint #0: do not silently swallow, mark fallback reason
                    eff_weight_cap = 0.05
                    try:
                        eff_weight_cap = canary_runner.get_effective_weight_cap(art)
                    except Exception:
                        pass
                    sub_scores.append(AgentSubScore(
                        agent_name=f"Synth_{art.name}",
                        ticker=ticker,
                        confidence=5.0,
                        factors={
                            "_fallback_reason": str(e),
                            "key_factor": "Factor Evaluation Failed",
                            "error": str(e),
                            "weight_cap": eff_weight_cap,
                        },
                        rationale=f"Evaluation failed: {e}",
                        timestamp=datetime.now().isoformat(),
                    ))
        except Exception as e:
            logger.warning("Failed to gather synthesized factor scores for %s: %s", ticker, e)

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

            # Extract JSON via resilient extractor
            data = _extract_score_object(response)
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

        base_scores = [s for s in sub_scores if not s.agent_name.startswith("Synth_") and s.agent_name != "Event_Bias"]
        synth_scores = [s for s in sub_scores if s.agent_name.startswith("Synth_")]
        event_bias_score = next((s for s in sub_scores if s.agent_name == "Event_Bias"), None)

        # Case 1: Standard 4-agent ensemble (no active synthesized factors)
        if not synth_scores:
            weighted_sum = 0.0
            total_weight = 0.0
            for score in base_scores:
                weight = self.agent_weights.get(score.agent_name.lower(), 0.25)
                weighted_sum += score.confidence * weight
                total_weight += weight

            composite = weighted_sum / total_weight if total_weight > 0 else 5.0
        else:
            # Case 2: Adaptive ensemble with synthesized factors
            # Total weight capped at 15% for all synthesized factors combined,
            # with individual factors respecting their stepped weight_cap.
            raw_synth_weights = [
                max(0.01, min(0.15, float(s.factors.get("weight_cap", 0.05))))
                for s in synth_scores
            ]
            sum_raw = sum(raw_synth_weights)
            if sum_raw > 0.15:
                scale_synth = 0.15 / sum_raw
                normalized_synth_weights = [w * scale_synth for w in raw_synth_weights]
            else:
                normalized_synth_weights = raw_synth_weights

            total_synth_weight = sum(normalized_synth_weights)
            base_scale = max(0.0, 1.0 - total_synth_weight)

            weighted_sum = 0.0
            total_weight = 0.0

            for score in base_scores:
                weight = self.agent_weights.get(score.agent_name.lower(), 0.25) * base_scale
                weighted_sum += score.confidence * weight
                total_weight += weight

            for score, w in zip(synth_scores, normalized_synth_weights):
                weighted_sum += score.confidence * w
                total_weight += w

            composite = weighted_sum / total_weight if total_weight > 0 else 5.0

        # Apply active micro event bias (個經事件偏置微調)
        if event_bias_score:
            micro_bias = float(event_bias_score.factors.get("current_impact", 0.0))
            composite = max(0.0, min(10.0, composite + micro_bias))

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

        # Macro stress integration (總經壓力動態調升防禦儲備)
        try:
            from src.services.event_impact_service import EventImpactService
            impact_svc = EventImpactService(user_id=self.user_id)
            _, extra_cash_ratio, _ = impact_svc.get_macro_stress_bias()
            reserve += extra_cash_ratio
        except Exception as e:
            logger.warning(f"CompositorService: failed to check macro stress for cash reserve: {e}")

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
        return int(hashlib.sha256(ticker.encode()).hexdigest()[:8], 16)

