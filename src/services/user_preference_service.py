"""
UserPreferenceService — aggregates interaction_feedback into an actionable
preference profile (Loop 3, B-P2.2): risk appetite, sector aversions, and
position-size comfort, plus a short prose summary injected into council
prompts (same pattern as agent_rules' General Rules injection).

Deterministic aggregation (pure SQL) + one fast-tier LLM call for the
prose summary — cheap, runs weekly.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, Optional

from sqlalchemy import text

logger = logging.getLogger(__name__)

LOOKBACK_DAYS = 90
SECTOR_AVERSION_THRESHOLD = 3  # reasoned rejections in a sector before it's flagged
# Reason codes that indicate genuine conviction against the trade (vs. e.g.
# bad_timing, which is more about the moment than the sector/thesis).
CONVICTION_REASON_CODES = {"too_risky", "wrong_ticker", "dont_trust_thesis"}


class UserPreferenceService:
    def __init__(self, user_id: str):
        self.user_id = user_id

    def _engine(self):
        from src.data.database import get_db_engine
        return get_db_engine()

    async def update_preferences(self) -> Optional[Dict[str, Any]]:
        """
        Recompute and persist this user's preference profile from the last
        LOOKBACK_DAYS of interaction_feedback. Returns the computed profile,
        or None if there's no feedback history yet (nothing to learn from).
        """
        rows = self._fetch_feedback()
        if not rows:
            return None

        risk_appetite = self._compute_risk_appetite(rows)
        position_comfort = self._compute_position_comfort(rows)
        sector_aversions = await self._compute_sector_aversions(rows)
        summary = await self._generate_summary(risk_appetite, position_comfort, sector_aversions, len(rows))

        profile = {
            "risk_appetite_score": risk_appetite,
            "position_comfort": position_comfort,
            "sector_aversions": sector_aversions,
            "summary_text": summary,
            "sample_size": len(rows),
        }
        self._persist(profile)
        return profile

    def _fetch_feedback(self):
        try:
            with self._engine().connect() as conn:
                # Bind the window as a parameter instead of interpolating it.
                # LOOKBACK_DAYS is a module constant, so this was never
                # injectable, but an f-string around SQL is the pattern bandit
                # B608 flags and the one this repo bans outright. Same idiom as
                # src/infrastructure/llm/cost_attribution.py:239.
                # 天數改用綁定參數；雖然 LOOKBACK_DAYS 是模組常數不可能被注入，
                # 但 SQL 內用 f-string 正是本專案明令禁止的寫法。
                return conn.execute(
                    text("""
                        SELECT decision, reason_code, ticker
                        FROM interaction_feedback
                        WHERE user_id = :uid
                          AND created_at > NOW() - (CAST(:lookback_days AS INTEGER) * INTERVAL '1 day')
                    """),
                    {"uid": self.user_id, "lookback_days": LOOKBACK_DAYS},
                ).fetchall()
        except Exception as e:
            logger.warning(f"UserPreference: failed to fetch feedback for {self.user_id}: {e}")
            return []

    @staticmethod
    def _compute_risk_appetite(rows) -> float:
        """Fraction approved among decided (non-expired) requests, scaled to [-1, 1]."""
        approved = sum(1 for r in rows if r.decision == "approved")
        rejected = sum(1 for r in rows if r.decision == "rejected")
        decided = approved + rejected
        if decided == 0:
            return 0.0
        return round((approved - rejected) / decided, 3)

    @staticmethod
    def _compute_position_comfort(rows) -> float:
        """Negative-leaning score: more 'position_too_large' rejections -> lower comfort."""
        rejected = sum(1 for r in rows if r.decision == "rejected")
        if rejected == 0:
            return 0.0
        too_large = sum(1 for r in rows if r.decision == "rejected" and r.reason_code == "position_too_large")
        return round(-(too_large / rejected), 3)

    async def _compute_sector_aversions(self, rows) -> Dict[str, int]:
        """Sector -> count of high-conviction reasoned rejections, sectors below threshold omitted."""
        by_ticker: Dict[str, int] = {}
        for r in rows:
            if r.decision == "rejected" and r.ticker and r.reason_code in CONVICTION_REASON_CODES:
                by_ticker[r.ticker] = by_ticker.get(r.ticker, 0) + 1
        if not by_ticker:
            return {}

        sector_counts: Dict[str, int] = {}
        for ticker, count in by_ticker.items():
            sector = await self._resolve_sector(ticker)
            if sector:
                sector_counts[sector] = sector_counts.get(sector, 0) + count
        return {s: c for s, c in sector_counts.items() if c >= SECTOR_AVERSION_THRESHOLD}

    async def _resolve_sector(self, ticker: str) -> Optional[str]:
        try:
            from src.services.market_data_service import MarketDataService
            mds = MarketDataService(user_id=self.user_id)
            info = mds.get_financials(ticker)
            return info.get("sector") if info else None
        except Exception as e:
            logger.debug(f"UserPreference: sector lookup failed for {ticker}: {e}")
            return None

    async def _generate_summary(
        self, risk_appetite: float, position_comfort: float,
        sector_aversions: Dict[str, int], sample_size: int,
    ) -> str:
        """One fast-tier call turning the numbers into a short prose block
        for prompt injection. Falls back to a templated string on failure."""
        fallback = self._templated_summary(risk_appetite, position_comfort, sector_aversions)
        try:
            from src.infrastructure.llm.llm_config_chain import build_config_chain
            from src.infrastructure.llm.resilient_pipeline import ResilientLLMPipeline
            from src.domain.interfaces import Message

            chain = build_config_chain(self.user_id, "fast")
            if not chain:
                return fallback
            pipeline = ResilientLLMPipeline(
                config_chain=chain, user_id=self.user_id,
                agent_name="PreferenceSummarizer", tier="fast",
            )
            prompt = (
                "Summarize this user's trading-approval behavior in 1-2 sentences "
                "for injection into an investment agent's context. Be concrete, "
                "not generic.\n\n"
                f"Risk appetite score ({sample_size} samples, -1=very averse to +1=very risk-seeking): {risk_appetite}\n"
                f"Position-size comfort (-1=often flags positions as too large, 0=neutral): {position_comfort}\n"
                f"Sectors with repeated reasoned rejections: {sector_aversions or 'none'}\n"
            )
            resp, _ = await pipeline.execute([Message(role="user", content=prompt)], temperature=0.3, max_tokens=120)
            return resp.strip() if resp else fallback
        except Exception as e:
            logger.debug(f"UserPreference: summary generation failed, using template: {e}")
            return fallback

    @staticmethod
    def _templated_summary(risk_appetite: float, position_comfort: float, sector_aversions: Dict[str, int]) -> str:
        appetite_desc = "risk-seeking" if risk_appetite > 0.2 else "risk-averse" if risk_appetite < -0.2 else "neutral"
        parts = [f"User trends {appetite_desc} (score {risk_appetite:+.2f})."]
        if position_comfort < -0.3:
            parts.append("Frequently flags position sizes as too large.")
        if sector_aversions:
            sectors = ", ".join(sector_aversions.keys())
            parts.append(f"Repeatedly rejected trades in: {sectors}.")
        return " ".join(parts)

    def _persist(self, profile: Dict[str, Any]) -> None:
        try:
            with self._engine().begin() as conn:
                conn.execute(
                    text("""
                        INSERT INTO user_preferences
                            (user_id, risk_appetite_score, sector_aversions, position_comfort, summary_text, sample_size, updated_at)
                        VALUES (:uid, :risk, :sectors, :comfort, :summary, :n, NOW())
                        ON CONFLICT (user_id) DO UPDATE SET
                            risk_appetite_score = EXCLUDED.risk_appetite_score,
                            sector_aversions = EXCLUDED.sector_aversions,
                            position_comfort = EXCLUDED.position_comfort,
                            summary_text = EXCLUDED.summary_text,
                            sample_size = EXCLUDED.sample_size,
                            updated_at = NOW()
                    """),
                    {
                        "uid": self.user_id,
                        "risk": profile["risk_appetite_score"],
                        "sectors": json.dumps(profile["sector_aversions"]),
                        "comfort": profile["position_comfort"],
                        "summary": profile["summary_text"],
                        "n": profile["sample_size"],
                    },
                )
        except Exception as e:
            logger.warning(f"UserPreference: failed to persist profile for {self.user_id}: {e}")

    def get_summary_text(self) -> str:
        """Read-only accessor for council prompt injection. Empty string if none computed yet."""
        try:
            with self._engine().connect() as conn:
                row = conn.execute(
                    text("SELECT summary_text FROM user_preferences WHERE user_id = :uid"),
                    {"uid": self.user_id},
                ).fetchone()
                return row[0] if row and row[0] else ""
        except Exception as e:
            logger.debug(f"UserPreference: get_summary_text failed for {self.user_id}: {e}")
            return ""

    def get_sector_penalty(self, sector: str) -> float:
        """
        Confidence penalty in [0, 1] for a given sector, derived from
        reasoned-rejection count (0 = no penalty). Callers (e.g. council
        confidence scoring) subtract this from a raw confidence score.
        """
        try:
            with self._engine().connect() as conn:
                row = conn.execute(
                    text("SELECT sector_aversions FROM user_preferences WHERE user_id = :uid"),
                    {"uid": self.user_id},
                ).fetchone()
                if not row or not row[0]:
                    return 0.0
                aversions = row[0] if isinstance(row[0], dict) else json.loads(row[0])
                count = aversions.get(sector, 0)
                return min(0.3, count * 0.1)  # capped — a hint, never an outright block
        except Exception as e:
            logger.debug(f"UserPreference: get_sector_penalty failed for {sector}: {e}")
            return 0.0
