"""
Council Debate Memory & Vector Retrieval Service (A3 Engine).
=============================================================================
Provides semantic contextual memory and outcome-anchored precedent retrieval
for the Agent Council (P5.2 / A1~A3).

Key Capabilities:
1. Episodic Contextual Memory:
   - Indexes Council debate minutes with text embeddings (nomic-embed-text 768-dim).
   - Links deliberations and consensus with post-trade decision outcomes (realized return, alpha, and lessons).
2. Outcome-Aware Precedent Retrieval:
   - Searches historical similar debates based on topic/query embeddings.
   - Enriches candidate precedents with actual ex-post alpha performance from `decision_outcomes`.
   - Re-ranks candidates using a multi-factor score:
     Score = 0.5 * Similarity + 0.2 * Recency + 0.3 * AttributionConfidence.
3. Prompt Precedent Synthesis:
   - Compiles retrieved historical precedents into structured prompt context,
     supplying explicit past wisdom, consensus decisions, and hard lessons to expert agents and the CIO.
4. Semantic Search & Transparency:
   - Powers the `/api/v1/council/memory/*` endpoints for semantic exploration of historical council debates.
"""
from __future__ import annotations

import json
import logging
import math
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import text

from src.config.owner import resolve_user_id
from src.data.database import get_db_engine
from src.repositories.vector_repository import AlchemyVectorRepository

logger = logging.getLogger(__name__)


@dataclass
class DebateOutcomeRecord:
    """Individual decision outcome associated with a debate session."""
    outcome_id: str
    ticker: str
    agent_name: str
    signal: str
    realized_return_pct: Optional[float]
    benchmark_return_pct: Optional[float]
    alpha_pct: Optional[float]
    lesson: Optional[str]
    resolved_at: Optional[str]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "outcome_id": self.outcome_id,
            "ticker": self.ticker,
            "agent_name": self.agent_name,
            "signal": self.signal,
            "realized_return_pct": round(self.realized_return_pct, 2) if self.realized_return_pct is not None else None,
            "benchmark_return_pct": round(self.benchmark_return_pct, 2) if self.benchmark_return_pct is not None else None,
            "alpha_pct": round(self.alpha_pct, 2) if self.alpha_pct is not None else None,
            "lesson": self.lesson,
            "resolved_at": self.resolved_at,
        }


@dataclass
class DebatePrecedent:
    """Historical debate precedent enriched with ex-post outcome attribution."""
    minute_id: str
    session_id: str
    topic: str
    consensus: str
    created_at: str
    similarity: float
    relevance_score: float
    outcomes: List[DebateOutcomeRecord] = field(default_factory=list)
    participants: Optional[str] = None
    transcript_preview: Optional[str] = None

    @property
    def has_attribution(self) -> bool:
        return any(o.alpha_pct is not None for o in self.outcomes)

    @property
    def avg_alpha_pct(self) -> Optional[float]:
        valid_alphas = [o.alpha_pct for o in self.outcomes if o.alpha_pct is not None]
        if not valid_alphas:
            return None
        return round(sum(valid_alphas) / len(valid_alphas), 2)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "minute_id": self.minute_id,
            "session_id": self.session_id,
            "topic": self.topic,
            "consensus": self.consensus,
            "created_at": self.created_at,
            "similarity": round(self.similarity, 4),
            "relevance_score": round(self.relevance_score, 4),
            "has_attribution": self.has_attribution,
            "avg_alpha_pct": self.avg_alpha_pct,
            "outcomes": [o.to_dict() for o in self.outcomes],
            "participants": self.participants,
            "transcript_preview": self.transcript_preview,
        }


@dataclass
class DebateRetrievalResult:
    """Container for precedent search results and synthesized LLM guidance."""
    precedents: List[DebatePrecedent]
    synthesized_prompt_context: str
    total_found: int
    query: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "query": self.query,
            "total_found": self.total_found,
            "synthesized_prompt_context": self.synthesized_prompt_context,
            "precedents": [p.to_dict() for p in self.precedents],
        }


class CouncilDebateMemoryService:
    """
    Council Debate Memory & Vector Retrieval Orchestrator (A3).
    """

    DEFAULT_SIMILARITY_THRESHOLD = 0.60
    DEFAULT_TOP_K = 3
    DEFAULT_RECENCY_WEIGHT = 0.20
    DEFAULT_ATTRIBUTION_BOOST = 0.30

    def __init__(
        self,
        user_id: str = "default_user",
        db_path: Optional[str] = None,
        vector_repo: Optional[AlchemyVectorRepository] = None,
        settings_service: Optional[Any] = None,
    ):
        self.user_id = resolve_user_id(user_id)
        self.engine = get_db_engine(db_path)
        self.vector_repo = vector_repo or AlchemyVectorRepository(engine=self.engine)
        self.settings_service = settings_service

    def _get_setting(self, key: str, default: Any, val_type: type = float) -> Any:
        """Helper to retrieve dynamic setting with fallback."""
        if not self.settings_service:
            return default
        try:
            val = self.settings_service.get_setting(key, default)
            if val is None:
                return default
            if val_type is bool:
                return str(val).lower() in ("true", "1", "yes")
            return val_type(val)
        except Exception:
            return default

    @property
    def is_enabled(self) -> bool:
        return self._get_setting("council_memory_retrieval_enabled", True, bool)

    @property
    def similarity_threshold(self) -> float:
        return float(self._get_setting("council_memory_similarity_threshold", self.DEFAULT_SIMILARITY_THRESHOLD, float))

    @property
    def default_top_k(self) -> int:
        return int(self._get_setting("council_memory_top_k", self.DEFAULT_TOP_K, int))

    def _embed_query(self, query: str) -> Optional[List[float]]:
        """Safely generate text embedding using system embedding service."""
        try:
            from src.infrastructure.llm.embedding_service import embed_text
            return embed_text(query)
        except Exception as e:
            logger.debug(f"Council memory embedding generation skipped: {e}")
            return None

    def retrieve_similar_precedents(
        self,
        topic: str,
        ticker: Optional[str] = None,
        limit: Optional[int] = None,
        threshold: Optional[float] = None,
    ) -> DebateRetrievalResult:
        """
        Search for top-K historical council debate precedents matching the given topic,
        enriched with post-trade alpha attribution and lessons from decision_outcomes.
        """
        k = limit or self.default_top_k
        thresh = threshold or self.similarity_threshold

        if not self.is_enabled:
            return DebateRetrievalResult(
                precedents=[],
                synthesized_prompt_context="",
                total_found=0,
                query=topic,
            )

        # 1. Vector or Text Search
        q_emb = self._embed_query(topic)
        raw_candidates: List[Dict[str, Any]] = []

        if q_emb:
            try:
                # Query top candidates via pgvector
                raw_candidates = self.vector_repo.search_similar_minutes_by_embedding(
                    embedding=q_emb,
                    user_id=self.user_id,
                    limit=max(k * 3, 10),
                    threshold=thresh,
                )
            except Exception as e:
                logger.warning(f"Vector search failed, falling back to text search: {e}")

        if not raw_candidates:
            # Fallback to full-text search
            try:
                raw_candidates = self.vector_repo.search_similar_minutes(
                    topic=topic,
                    user_id=self.user_id,
                    limit=max(k * 3, 10),
                )
            except Exception as e:
                logger.warning(f"Full text search also failed: {e}")

        if not raw_candidates:
            return DebateRetrievalResult(
                precedents=[],
                synthesized_prompt_context="No past council precedents found.",
                total_found=0,
                query=topic,
            )

        # 2. Extract Session IDs and Ingest Decision Outcomes
        session_ids = [c.get("session_id") or c.get("id") for c in raw_candidates if c.get("id")]
        outcomes_by_session = self._fetch_outcomes_for_sessions(session_ids)

        # 3. Enrich & Re-rank Precedents
        precedents: List[DebatePrecedent] = []
        now_dt = datetime.now(timezone.utc)

        for cand in raw_candidates:
            sid = cand.get("session_id") or cand.get("id", "")
            mid = cand.get("id", "")
            topic_str = cand.get("topic", "")
            consensus_str = cand.get("consensus", "")
            sim = float(cand.get("similarity", cand.get("rank", 0.70)))
            created_at_val = cand.get("created_at")

            # Parse created_at
            if isinstance(created_at_val, datetime):
                c_dt = created_at_val
                c_str = created_at_val.isoformat()
            elif isinstance(created_at_val, str):
                c_str = created_at_val
                try:
                    c_dt = datetime.fromisoformat(created_at_val.replace("Z", "+00:00"))
                except Exception:
                    c_dt = now_dt
            else:
                c_dt = now_dt
                c_str = now_dt.isoformat()

            # Matched outcomes for this debate
            matched_outcomes = outcomes_by_session.get(sid, [])
            has_resolved = any(o.alpha_pct is not None for o in matched_outcomes)

            # Compute Recency Decay (30 days half-life)
            age_days = max(0.0, (now_dt - c_dt).total_seconds() / 86400.0)
            recency_score = math.exp(-age_days / 30.0)

            # Attribution Confidence Bonus
            attribution_score = 0.0
            if has_resolved:
                attribution_score = 1.0
                # Extra boost if the precedent captured a severe failure or high outperformance
                max_alpha = max(abs(o.alpha_pct or 0.0) for o in matched_outcomes)
                if max_alpha > 5.0:
                    attribution_score += 0.5

            # Multi-Factor Re-Ranking Score
            composite_score = (
                0.50 * sim +
                self.DEFAULT_RECENCY_WEIGHT * recency_score +
                self.DEFAULT_ATTRIBUTION_BOOST * attribution_score
            )

            # Ticker relevance match boost
            if ticker and ticker.upper() in topic_str.upper():
                composite_score += 0.20

            precedents.append(
                DebatePrecedent(
                    minute_id=mid,
                    session_id=sid,
                    topic=topic_str,
                    consensus=consensus_str,
                    created_at=c_str,
                    similarity=sim,
                    relevance_score=composite_score,
                    outcomes=matched_outcomes,
                    participants=cand.get("participants"),
                )
            )

        # Sort descending by composite relevance score
        precedents.sort(key=lambda p: p.relevance_score, reverse=True)
        top_precedents = precedents[:k]

        # 4. Synthesize Markdown Prompt Block
        prompt_guidance = self.synthesize_precedents_for_prompt(top_precedents)

        return DebateRetrievalResult(
            precedents=top_precedents,
            synthesized_prompt_context=prompt_guidance,
            total_found=len(precedents),
            query=topic,
        )

    def _fetch_outcomes_for_sessions(self, session_ids: List[str]) -> Dict[str, List[DebateOutcomeRecord]]:
        """Batch query decision outcomes for a list of session IDs."""
        if not session_ids:
            return {}

        results: Dict[str, List[DebateOutcomeRecord]] = {}
        try:
            with self.engine.connect() as conn:
                # Query outcomes matching session_ids or user_id
                q = text("""
                    SELECT id, session_id, ticker, agent_name, signal,
                           realized_return_pct, benchmark_return_pct, alpha_pct,
                           lesson, resolved_at
                    FROM decision_outcomes
                    WHERE session_id IN :sids AND user_id = :uid
                    ORDER BY decided_at DESC
                """)
                rows = conn.execute(q, {"sids": tuple(session_ids), "uid": self.user_id}).fetchall()

                for r in rows:
                    sid = r.session_id
                    rec = DebateOutcomeRecord(
                        outcome_id=r.id,
                        ticker=r.ticker,
                        agent_name=r.agent_name,
                        signal=r.signal,
                        realized_return_pct=float(r.realized_return_pct) if r.realized_return_pct is not None else None,
                        benchmark_return_pct=float(r.benchmark_return_pct) if r.benchmark_return_pct is not None else None,
                        alpha_pct=float(r.alpha_pct) if r.alpha_pct is not None else None,
                        lesson=r.lesson,
                        resolved_at=r.resolved_at.isoformat() if r.resolved_at else None,
                    )
                    results.setdefault(sid, []).append(rec)
        except Exception as e:
            logger.warning(f"Error fetching decision outcomes for sessions: {e}")

        return results

    def synthesize_precedents_for_prompt(self, precedents: List[DebatePrecedent]) -> str:
        """
        Synthesize retrieved precedents into a concise, high-signal Markdown block
        for LLM prompt injection (into Council System Prompts and CIO Final Verdict).
        """
        if not precedents:
            return "No historical council precedents found for this market context."

        lines: List[str] = [
            "### 🏛️ 評議會歷史相似辯論前例與事後歸因 (Council Debate Precedents & Attribution):"
        ]

        for idx, prec in enumerate(precedents, start=1):
            date_part = prec.created_at[:10] if len(prec.created_at) >= 10 else "Unknown Date"
            lines.append(f"- 【先例 #{idx}】議題: \"{prec.topic}\" ({date_part}, 關聯度: {prec.relevance_score:.2f}):")

            # Consensus preview
            consensus_clean = (prec.consensus or "").strip().replace("\n", " ")
            if len(consensus_clean) > 120:
                consensus_clean = consensus_clean[:120] + "..."
            lines.append(f"  * 歷史共識裁決: {consensus_clean or '無共識紀錄'}")

            # Post-trade outcome attribution
            if prec.has_attribution:
                for outcome in prec.outcomes:
                    alpha_str = f"{outcome.alpha_pct:+.2f}%" if outcome.alpha_pct is not None else "N/A"
                    ret_str = f"{outcome.realized_return_pct:+.2f}%" if outcome.realized_return_pct is not None else "N/A"
                    lines.append(f"  * 事後結算表現: [{outcome.ticker}] 訊號={outcome.signal}, 實現報酬={ret_str}, 基準超額 Alpha={alpha_str}")
                    if outcome.lesson:
                        lesson_clean = outcome.lesson.strip().replace("\n", " ")
                        if len(lesson_clean) > 140:
                            lesson_clean = lesson_clean[:140] + "..."
                        lines.append(f"  * 事後經驗教訓: \"{lesson_clean}\"")
            else:
                lines.append("  * 事後結算表現: [尚未結算 / 觀測期中]")

        return "\n".join(lines)

    def search_debates_api(
        self,
        query: str,
        ticker: Optional[str] = None,
        min_alpha: Optional[float] = None,
        limit: int = 10,
    ) -> List[DebatePrecedent]:
        """
        API helper for interactive search with multi-dimensional filtering.
        """
        result = self.retrieve_similar_precedents(
            topic=query,
            ticker=ticker,
            limit=limit,
        )

        filtered = result.precedents
        if min_alpha is not None:
            filtered = [
                p for p in filtered
                if p.avg_alpha_pct is not None and p.avg_alpha_pct >= min_alpha
            ]

        return filtered

    def get_debate_detail(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Fetch complete transcript, consensus, and all associated outcome records for a session."""
        try:
            with self.engine.connect() as conn:
                q = text("""
                    SELECT id, session_id, user_id, topic, participants, consensus, transcript, created_at
                    FROM council_minutes
                    WHERE (session_id = :sid OR id = :sid) AND user_id = :uid
                    LIMIT 1
                """)
                row = conn.execute(q, {"sid": session_id, "uid": self.user_id}).fetchone()
                if not row:
                    return None

                # Fetch outcomes
                outcomes_map = self._fetch_outcomes_for_sessions([row.session_id])
                outcomes = outcomes_map.get(row.session_id, [])

                return {
                    "minute_id": row.id,
                    "session_id": row.session_id,
                    "user_id": row.user_id,
                    "topic": row.topic,
                    "participants": row.participants,
                    "consensus": row.consensus,
                    "transcript": row.transcript,
                    "created_at": row.created_at.isoformat() if row.created_at else None,
                    "outcomes": [o.to_dict() for o in outcomes],
                }
        except Exception as e:
            logger.error(f"Error getting debate detail for session {session_id}: {e}")
            return None
