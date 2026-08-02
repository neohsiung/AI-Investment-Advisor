"""
Decision->outcome memory with alpha-anchored reflection (P1 learning loop).

Two-phase design (pattern adapted from TradingAgents graph/reflection.py,
reimplemented for this stack):

  Phase A (record_decision): store the decision as PENDING the moment it's
  made — ticker, signal, price, horizon.

  Phase B (resolve_pending): on a later run, for any decision whose horizon
  has elapsed, fetch the realized return and a benchmark (SPY) return over
  the same window, compute alpha = realized - benchmark, and ask a cheap
  model for a short lesson that must cite the alpha figure.

This replaces `experience_replay_service.analyze_narrative_drift`'s
self-grading (LLM eyeballs market data and picks a 1-10 score with no ground
truth) with something falsifiable: the number comes from real price data.

決策→結果記憶：兩階段。決策當下記為 pending；到期後抓實現報酬 vs 基準
（SPY），算 alpha，讓便宜模型寫引用 alpha 數字的教訓。取代不可證偽的自評。
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import text

from src.data.database import get_db_engine

logger = logging.getLogger(__name__)

DEFAULT_HORIZON_DAYS = 5
DEFAULT_BENCHMARK = "SPY"


class OutcomeReflectionService:
    def __init__(self, user_id: str, db_path: Optional[str] = None):
        self.user_id = user_id
        self.engine = get_db_engine(db_path)

    # ── Phase A: record ──────────────────────────────────────────────

    def record_decision(
        self,
        ticker: str,
        agent_name: str,
        signal: str,
        price: float,
        session_id: Optional[str] = None,
        horizon_days: int = DEFAULT_HORIZON_DAYS,
    ) -> Optional[str]:
        """Store a decision as pending. Never raises — logging must not block trading."""
        if not ticker or not price:
            return None
        try:
            rec_id = str(uuid.uuid4())
            with self.engine.begin() as conn:
                conn.execute(text("""
                    INSERT INTO decision_outcomes
                        (id, user_id, session_id, agent_name, ticker, signal,
                         price_at_decision, horizon_days)
                    VALUES
                        (:id, :user_id, :session_id, :agent_name, :ticker, :signal,
                         :price, :horizon_days)
                """), {
                    "id": rec_id, "user_id": self.user_id, "session_id": session_id,
                    "agent_name": agent_name, "ticker": ticker, "signal": signal,
                    "price": price, "horizon_days": horizon_days,
                })
            return rec_id
        except Exception as exc:
            logger.warning("record_decision failed (non-blocking): %s", exc)
            return None

    # ── Phase B: resolve ─────────────────────────────────────────────

    def resolve_pending(self, max_batch: int = 50) -> Dict[str, Any]:
        """
        Resolve decisions whose horizon has elapsed: fetch realized + benchmark
        returns, compute alpha, generate a lesson. Returns a summary dict.
        Safe to call repeatedly (idempotent — only touches resolved_at IS NULL rows).
        """
        rows = self._fetch_due_pending(max_batch)
        resolved = 0
        skipped = 0
        failed = 0
        for row in rows:
            try:
                if self._resolve_one(row):
                    resolved += 1
                else:
                    skipped += 1  # not due yet, or price data unavailable this run
            except Exception as exc:
                logger.warning("resolve_pending: failed for %s (%s): %s", row["ticker"], row["id"], exc)
                failed += 1
        return {"checked": len(rows), "resolved": resolved, "skipped": skipped, "failed": failed}

    def _fetch_due_pending(self, max_batch: int) -> List[Dict[str, Any]]:
        with self.engine.connect() as conn:
            result = conn.execute(text("""
                SELECT id, user_id, agent_name, ticker, signal, price_at_decision, decided_at, horizon_days
                FROM decision_outcomes
                WHERE user_id = :user_id AND resolved_at IS NULL
                  AND decided_at <= :cutoff
                ORDER BY decided_at ASC
                LIMIT :limit
            """), {
                "user_id": self.user_id,
                # horizon_days varies per row; over-fetch with a generous cutoff
                # (30d) and let _resolve_one re-check the row's own horizon.
                "cutoff": datetime.now(timezone.utc) - timedelta(days=0),
                "limit": max_batch,
            })
            return [dict(r._mapping) for r in result]

    def _resolve_one(self, row: Dict[str, Any]) -> bool:
        """Returns True if the row was actually resolved (updated), False if
        skipped (not due yet, or price data unavailable this run — retried
        on the next call)."""
        decided_at = row["decided_at"]
        if decided_at.tzinfo is None:
            decided_at = decided_at.replace(tzinfo=timezone.utc)
        horizon_days = int(row["horizon_days"] or DEFAULT_HORIZON_DAYS)
        due_at = decided_at + timedelta(days=horizon_days)
        if datetime.now(timezone.utc) < due_at:
            return False  # not due yet, skip silently

        ticker = row["ticker"]
        price_then = float(row["price_at_decision"])
        current_price = self._fetch_price(ticker)
        benchmark_then, benchmark_now = self._fetch_benchmark_window(decided_at, due_at)
        if current_price is None or not benchmark_then or not benchmark_now or price_then <= 0:
            logger.debug("resolve_pending: insufficient price data for %s, skipping", ticker)
            return False

        realized_pct = (current_price - price_then) / price_then * 100.0
        benchmark_pct = (benchmark_now - benchmark_then) / benchmark_then * 100.0
        alpha_pct = realized_pct - benchmark_pct

        lesson = self._generate_lesson(ticker, row["signal"], realized_pct, benchmark_pct, alpha_pct)

        if alpha_pct < 0:
            agent_name = row.get("agent_name") or "CIO"
            self._distill_failure(agent_name, ticker, row["signal"], realized_pct, benchmark_pct, alpha_pct, decision_id=row.get("id"))

        # B-P2.1: EWMA-update the score of every rule cited for this
        # decision — zero extra LLM cost (pure SQL), gives per-rule alpha
        # attribution without a dedicated scoring pass.
        if row.get("id"):
            try:
                from src.services.rule_lifecycle_service import RuleLifecycleService
                RuleLifecycleService(user_id=self.user_id).backfill_score(row["id"], alpha_pct)
            except Exception as score_e:
                logger.debug(f"resolve_pending: rule score backfill skipped for {ticker}: {score_e}")

        with self.engine.begin() as conn:
            conn.execute(text("""
                UPDATE decision_outcomes
                SET resolved_at = :resolved_at, realized_return_pct = :realized,
                    benchmark_return_pct = :benchmark, alpha_pct = :alpha, lesson = :lesson
                WHERE id = :id
            """), {
                "resolved_at": datetime.now(timezone.utc), "realized": round(realized_pct, 4),
                "benchmark": round(benchmark_pct, 4), "alpha": round(alpha_pct, 4),
                "lesson": lesson, "id": row["id"],
            })
        return True

    def _fetch_price(self, ticker: str) -> Optional[float]:
        try:
            import yfinance as yf
            hist = yf.Ticker(ticker).history(period="5d")
            if hist.empty:
                return None
            return float(hist["Close"].iloc[-1])
        except Exception as exc:
            logger.debug("_fetch_price(%s) failed: %s", ticker, exc)
            return None

    def _fetch_benchmark_window(self, start: datetime, end: datetime) -> tuple:
        """Return (price_at_start, price_at_end) for the benchmark ticker."""
        try:
            import yfinance as yf
            hist = yf.Ticker(DEFAULT_BENCHMARK).history(
                start=start.strftime("%Y-%m-%d"),
                end=(end + timedelta(days=2)).strftime("%Y-%m-%d"),
            )
            if hist.empty or len(hist) < 2:
                return None, None
            return float(hist["Close"].iloc[0]), float(hist["Close"].iloc[-1])
        except Exception as exc:
            logger.debug("_fetch_benchmark_window failed: %s", exc)
            return None, None

    def _generate_lesson(self, ticker: str, signal: str, realized_pct: float,
                          benchmark_pct: float, alpha_pct: float) -> str:
        """Ask a cheap model for a 2-4 sentence lesson that must cite the alpha figure."""
        try:
            import asyncio
            from src.infrastructure.llm.llm_config_chain import build_config_chain
            from src.infrastructure.llm.resilient_pipeline import ResilientLLMPipeline
            from src.domain.interfaces import Message

            chain = build_config_chain(self.user_id, "fast")
            if not chain:
                return self._fallback_lesson(ticker, signal, alpha_pct)

            prompt = (
                f"A trading decision on {ticker} was rated {signal}. "
                f"Realized return over the horizon: {realized_pct:+.2f}%. "
                f"Benchmark (SPY) return: {benchmark_pct:+.2f}%. "
                f"Alpha (realized - benchmark): {alpha_pct:+.2f}%.\n"
                "Write a 2-4 sentence lesson for future decisions on this ticker. "
                "You MUST cite the alpha figure explicitly. Be concrete and specific, "
                "not generic platitudes."
            )
            pipeline = ResilientLLMPipeline(
                config_chain=chain, user_id=self.user_id,
                agent_name="OutcomeReflector", tier="fast",
            )

            async def _run():
                resp, _ = await pipeline.execute(
                    [Message(role="user", content=prompt)], temperature=0.4, max_tokens=200,
                )
                return resp

            try:
                loop = asyncio.get_running_loop()
                # already in an event loop (e.g. called from async code) — run in a fresh loop via thread
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as ex:
                    return ex.submit(lambda: asyncio.run(_run())).result()
            except RuntimeError:
                return asyncio.run(_run())
        except Exception as exc:
            logger.debug("_generate_lesson LLM call failed (%s); using fallback", exc)
            return self._fallback_lesson(ticker, signal, alpha_pct)

    @staticmethod
    def _fallback_lesson(ticker: str, signal: str, alpha_pct: float) -> str:
        direction = "outperformed" if alpha_pct > 0 else "underperformed"
        return (
            f"The {signal} call on {ticker} {direction} the SPY benchmark by "
            f"{abs(alpha_pct):.2f}pp over the horizon."
        )

    def _distill_failure(self, agent_name: str, ticker: str, signal: str, realized_pct: float, benchmark_pct: float, alpha_pct: float, decision_id: Optional[str] = None) -> None:
        """
        Distill a failure rule and persist it as ONE new atomic
        agent_rules row (via AgentState.add_rule, not the old
        load-append-save blob pattern — atomic rows are required for
        per-rule citation/scoring in B-P2.1). Tagged with source_decision_id
        so the rule's provenance is traceable.
        """
        try:
            import asyncio
            from src.infrastructure.llm.llm_config_chain import build_config_chain
            from src.infrastructure.llm.resilient_pipeline import ResilientLLMPipeline
            from src.domain.interfaces import Message
            from src.repositories.memory_repository import AgentState

            chain = build_config_chain(self.user_id, "advanced")
            if not chain:
                return

            prompt = (
                f"A decision on {ticker} by agent {agent_name} resulted in negative alpha.\n"
                f"Signal: {signal}\n"
                f"Realized return: {realized_pct:+.2f}%\n"
                f"Benchmark return: {benchmark_pct:+.2f}%\n"
                f"Alpha: {alpha_pct:+.2f}%\n\n"
                f"Formulate a single concise, actionable general rule to avoid similar failures in the future. "
                f"The rule must be starting with a bullet point and be extremely specific (e.g., 'Avoid buying high-Beta stocks solely based on Momentum signals within 3 days of earnings releases')."
            )

            pipeline = ResilientLLMPipeline(
                config_chain=chain, user_id=self.user_id,
                agent_name="FailureDistiller", tier="advanced"
            )

            async def _run():
                resp, _ = await pipeline.execute(
                    [Message(role="user", content=prompt)], temperature=0.3, max_tokens=150
                )
                return resp

            try:
                loop = asyncio.get_running_loop()
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as ex:
                    rule = ex.submit(lambda: asyncio.run(_run())).result()
            except RuntimeError:
                rule = asyncio.run(_run())

            if rule:
                agent_state = AgentState()
                clean_rule = rule.strip().lstrip("- ")
                agent_state.add_rule(
                    agent_name, f"- {clean_rule}", user_id=self.user_id,
                    source_decision_id=decision_id,
                    status="candidate",
                )
                logger.info(f"Distilled and saved failure rule for {agent_name} (user={self.user_id})")
        except Exception as exc:
            logger.warning("_distill_failure failed (non-blocking): %s", exc)

    # ── Recall for prompt injection ──────────────────────────────────

    def get_past_context(self, ticker: Optional[str] = None, limit: int = 5) -> str:
        """
        Return a short markdown block of past resolved decisions + lessons for
        prompt injection: same-ticker history (if ticker given) plus recent
        cross-ticker lessons. Empty string if nothing resolved yet.
        """
        try:
            same_ticker: List[Dict[str, Any]] = []
            if ticker:
                with self.engine.connect() as conn:
                    result = conn.execute(text("""
                        SELECT ticker, signal, alpha_pct, lesson, decided_at
                        FROM decision_outcomes
                        WHERE user_id = :user_id AND ticker = :ticker AND resolved_at IS NOT NULL
                        ORDER BY decided_at DESC LIMIT :limit
                    """), {"user_id": self.user_id, "ticker": ticker, "limit": limit}).fetchall()
                    same_ticker = [dict(r._mapping) for r in result]

            with self.engine.connect() as conn:
                cross_q = """
                    SELECT ticker, signal, alpha_pct, lesson, decided_at
                    FROM decision_outcomes
                    WHERE user_id = :user_id AND resolved_at IS NOT NULL
                """
                params = {"user_id": self.user_id, "limit": limit}
                if ticker:
                    cross_q += " AND ticker != :ticker"
                    params["ticker"] = ticker
                cross_q += " ORDER BY decided_at DESC LIMIT :limit"
                cross = [dict(r._mapping) for r in conn.execute(text(cross_q), params).fetchall()]

            if not same_ticker and not cross:
                return ""

            lines = []
            if same_ticker:
                lines.append(f"Past decisions on {ticker}:")
                for r in same_ticker:
                    lines.append(f"  - [{r['decided_at']:%Y-%m-%d}] {r['signal']} alpha={float(r['alpha_pct']):+.2f}%: {r['lesson']}")
            if cross:
                lines.append("Recent cross-ticker lessons:")
                for r in cross:
                    lines.append(f"  - [{r['decided_at']:%Y-%m-%d}] {r['ticker']} {r['signal']} alpha={float(r['alpha_pct']):+.2f}%: {r['lesson']}")
            return "\n".join(lines)
        except Exception as exc:
            logger.debug("get_past_context failed (non-blocking): %s", exc)
            return ""
