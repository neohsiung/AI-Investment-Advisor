"""
RuleLifecycleService — citation tracking, alpha-based scoring, dedup, and
expiry for distilled agent_rules (Loop 1, B-P2.1).

Design (per approved plan):
  - Citation: at council time, one nano-tier call judges which active
    rules actually applied to the current decision (not N calls per rule
    — one batched call over the whole active rule set for that agent).
  - Scoring: when OutcomeReflectionService resolves a decision's alpha,
    every rule cited (applied=True) for that decision has its score
    updated as an EWMA over cited-decision alpha. This gives per-rule
    attribution with ZERO extra LLM cost at resolution time — the score
    update is pure SQL.
  - Dedup/contradiction: weekly, pgvector cosine similarity >0.85 pairs
    within an agent's active rule set go to an advanced-tier LLM judge
    (merge / contradicts / distinct).
  - Expiry: rules with <2 citations in 60 days, or a low score, are
    retired (kept for audit — status flips, never deleted).
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import text

logger = logging.getLogger(__name__)

EWMA_ALPHA = 0.3  # weight on the newest citation's alpha
EXPIRY_MIN_CITATIONS = 2
EXPIRY_WINDOW_DAYS = 60
EXPIRY_SCORE_FLOOR = -5.0  # rules whose EWMA alpha is this bad get retired even with enough citations
DEDUP_SIMILARITY_THRESHOLD = 0.85

# Gating constants (C4)
GATE_MIN_MATCHES = 3
GATE_PASS_ALPHA_CEILING = -0.5
GATE_SAMPLE_LIMIT = 40
GATE_PROVISIONAL_TTL_DAYS = 30



class RuleLifecycleService:
    def __init__(self, user_id: Optional[str] = None):
        import os
        self.user_id = user_id or os.getenv("PRIMARY_USER_ID") or os.getenv("USER_ID")
        if not self.user_id:
            from src.repositories.user_repository import AlchemyUserRepository
            self.user_id = AlchemyUserRepository().get_first_user_id()

    def _engine(self):
        from src.data.database import get_db_engine
        return get_db_engine()

    # ── Citation (called from council_service after loading rules) ──────

    async def judge_and_cite(
        self, agent_name: str, decision_id: str, decision_context: str,
        active_rules: List[Dict[str, Any]],
    ) -> List[int]:
        """
        One nano-tier call over the WHOLE active rule set for this agent,
        asking which rule ids actually applied to this decision. Returns
        the list of applied rule ids (also recorded to rule_citations).
        Empty list (and no LLM call) if there are no active rules.
        """
        if not active_rules:
            return []
        try:
            from src.agents.structured import invoke_structured
            from src.infrastructure.llm.llm_config_chain import build_config_chain
            from src.infrastructure.llm.resilient_pipeline import ResilientLLMPipeline
            from src.domain.interfaces import Message
            from pydantic import BaseModel, Field

            class _CitedRules(BaseModel):
                applied_rule_ids: List[int] = Field(default_factory=list)

            chain = build_config_chain(self.user_id, "nano")
            if not chain:
                return []
            pipeline = ResilientLLMPipeline(
                config_chain=chain, user_id=self.user_id,
                agent_name="RuleCitationJudge", tier="nano",
            )
            gateway = pipeline._gateway_factory(chain[0])
            config = pipeline._build_llm_config(chain[0], temperature=0.0, max_tokens=200)

            rules_listing = "\n".join(f"[{r['id']}] {r['rule_text']}" for r in active_rules)
            prompt = (
                f"Decision context for agent {agent_name}:\n{decision_context[:1000]}\n\n"
                f"Candidate rules (id: text):\n{rules_listing}\n\n"
                "Which rule ids were actually relevant/applicable to this decision? "
                "Return only ids that clearly apply; empty list if none do."
            )
            parsed, _raw = await invoke_structured(
                gateway, [Message(role="user", content=prompt)], config, _CitedRules,
            )
            applied_ids = parsed.applied_rule_ids if parsed else []
        except Exception as e:
            logger.debug(f"RuleLifecycle: citation judging failed (non-blocking): {e}")
            return []

        valid_ids = {r["id"] for r in active_rules}
        applied_ids = [rid for rid in applied_ids if rid in valid_ids]
        if applied_ids:
            self._record_citations(applied_ids, decision_id)
        return applied_ids

    def _record_citations(self, rule_ids: List[int], decision_id: str) -> None:
        try:
            with self._engine().begin() as conn:
                for rule_id in rule_ids:
                    conn.execute(
                        text("""
                            INSERT INTO rule_citations (rule_id, decision_id, applied)
                            VALUES (:rid, :did, TRUE)
                        """),
                        {"rid": rule_id, "did": decision_id},
                    )
                    conn.execute(
                        text("UPDATE agent_rules SET times_cited = times_cited + 1 WHERE id = :rid"),
                        {"rid": rule_id},
                    )
        except Exception as e:
            logger.warning(f"RuleLifecycle: failed to record citations: {e}")

    # ── Scoring (called from OutcomeReflectionService on resolution) ────

    def backfill_score(self, decision_id: str, alpha_pct: float) -> int:
        """
        Pure-SQL EWMA update: every rule cited for this decision gets
        score = (1-EWMA_ALPHA)*old_score + EWMA_ALPHA*alpha_pct. Also
        backfills rule_citations.alpha_pct for audit. Returns rows updated.
        """
        try:
            with self._engine().begin() as conn:
                conn.execute(
                    text("UPDATE rule_citations SET alpha_pct = :alpha WHERE decision_id = :did"),
                    {"alpha": alpha_pct, "did": decision_id},
                )
                result = conn.execute(
                    text("""
                        UPDATE agent_rules
                        SET score = (1 - :ewma) * score + :ewma * :alpha
                        WHERE id IN (
                            SELECT rule_id FROM rule_citations WHERE decision_id = :did AND applied = TRUE
                        )
                    """),
                    {"ewma": EWMA_ALPHA, "alpha": alpha_pct, "did": decision_id},
                )
                return result.rowcount
        except Exception as e:
            logger.warning(f"RuleLifecycle: backfill_score failed for decision {decision_id}: {e}")
            return 0

    # ── Weekly curation: expiry + dedup/contradiction ───────────────────

    def expire_stale_rules(self, user_id: Optional[str] = None) -> int:
        """
        Retire (status='retired') active rules that are either under-cited
        after EXPIRY_WINDOW_DAYS, have a consistently bad score, or have expired.
        Kept for audit, never deleted.
        """
        uid = user_id or self.user_id
        try:
            with self._engine().begin() as conn:
                result = conn.execute(
                    text("""
                        UPDATE agent_rules
                        SET status = 'retired', updated_at = NOW()
                        WHERE user_id = :uid AND status = 'active'
                          AND (
                            (created_at < NOW() - (:days || ' days')::interval AND (times_cited < :min_citations OR score < :floor))
                            OR (expires_at IS NOT NULL AND expires_at < NOW())
                          )
                    """),
                    {"uid": uid, "days": EXPIRY_WINDOW_DAYS, "min_citations": EXPIRY_MIN_CITATIONS, "floor": EXPIRY_SCORE_FLOOR},
                )
                if result.rowcount:
                    logger.info(f"RuleLifecycle: retired {result.rowcount} stale rule(s) for user {uid}")
                return result.rowcount
        except Exception as e:
            logger.warning(f"RuleLifecycle: expire_stale_rules failed: {e}")
            return 0

    async def dedupe_agent_rules(self, agent_name: str, user_id: Optional[str] = None) -> int:
        """
        Find near-duplicate active rule pairs (cosine >0.85) for one agent
        and ask an advanced-tier judge to merge/mark-contradictory/leave
        distinct. Returns the number of rules retired as duplicates.
        Requires embeddings to already be populated (see backfill task) —
        rules with no embedding are skipped, not treated as unique.
        """
        uid = user_id or self.user_id
        try:
            with self._engine().connect() as conn:
                pairs = conn.execute(
                    text("""
                        SELECT a.id AS id_a, a.rule_text AS text_a, b.id AS id_b, b.rule_text AS text_b,
                               1 - (a.embedding <=> b.embedding) AS similarity
                        FROM agent_rules a
                        JOIN agent_rules b
                          ON a.user_id = b.user_id AND a.agent_name = b.agent_name AND a.id < b.id
                        WHERE a.user_id = :uid AND a.agent_name = :name
                          AND a.status = 'active' AND b.status = 'active'
                          AND a.embedding IS NOT NULL AND b.embedding IS NOT NULL
                          AND 1 - (a.embedding <=> b.embedding) > :threshold
                    """),
                    {"uid": uid, "name": agent_name, "threshold": DEDUP_SIMILARITY_THRESHOLD},
                ).fetchall()
        except Exception as e:
            logger.warning(f"RuleLifecycle: dedupe query failed for {agent_name}: {e}")
            return 0

        if not pairs:
            return 0

        retired = 0
        for pair in pairs:
            verdict = await self._judge_pair(pair.text_a, pair.text_b)
            if verdict == "duplicate":
                # Retire the newer/lower-cited one, keep the other.
                try:
                    with self._engine().begin() as conn:
                        conn.execute(
                            text("""
                                UPDATE agent_rules SET status = 'retired', updated_at = NOW()
                                WHERE id = (
                                    SELECT id FROM agent_rules WHERE id IN (:a, :b)
                                    ORDER BY times_cited ASC, created_at DESC LIMIT 1
                                )
                            """),
                            {"a": pair.id_a, "b": pair.id_b},
                        )
                    retired += 1
                except Exception as e:
                    logger.warning(f"RuleLifecycle: failed to retire duplicate rule pair ({pair.id_a},{pair.id_b}): {e}")
        return retired

    async def _judge_pair(self, text_a: str, text_b: str) -> str:
        """Returns 'duplicate', 'contradicts', or 'distinct'."""
        try:
            from src.infrastructure.llm.llm_config_chain import build_config_chain
            from src.infrastructure.llm.resilient_pipeline import ResilientLLMPipeline
            from src.domain.interfaces import Message

            chain = build_config_chain(self.user_id, "advanced")
            if not chain:
                return "distinct"
            pipeline = ResilientLLMPipeline(
                config_chain=chain, user_id=self.user_id,
                agent_name="RuleDedupJudge", tier="advanced",
            )
            prompt = (
                "Two trading rules for the same agent:\n"
                f"A: {text_a}\nB: {text_b}\n\n"
                "Are they functionally duplicate (same constraint), contradictory "
                "(one allows what the other forbids), or distinct? "
                "Reply with exactly one word: duplicate, contradicts, or distinct."
            )
            resp, _ = await pipeline.execute([Message(role="user", content=prompt)], temperature=0.0, max_tokens=10)
            verdict = (resp or "").strip().lower()
            return verdict if verdict in ("duplicate", "contradicts", "distinct") else "distinct"
        except Exception as e:
            logger.debug(f"RuleLifecycle: pair judging failed (non-blocking): {e}")
            return "distinct"

    async def backfill_embeddings(self, agent_name: str, user_id: Optional[str] = None) -> int:
        """Embed any active rule missing an embedding (needed before dedup can run)."""
        uid = user_id or self.user_id
        try:
            with self._engine().connect() as conn:
                rows = conn.execute(
                    text("""
                        SELECT id, rule_text FROM agent_rules
                        WHERE user_id = :uid AND agent_name = :name AND status = 'active' AND embedding IS NULL
                    """),
                    {"uid": uid, "name": agent_name},
                ).fetchall()
        except Exception as e:
            logger.warning(f"RuleLifecycle: backfill_embeddings query failed for {agent_name}: {e}")
            return 0

        if not rows:
            return 0

        from src.infrastructure.llm.embedding_service import embed_text
        updated = 0
        for row in rows:
            try:
                emb = embed_text(row.rule_text)
                if not emb:
                    continue
                with self._engine().begin() as conn:
                    conn.execute(
                        text("UPDATE agent_rules SET embedding = :emb WHERE id = :id"),
                        {"emb": str(emb), "id": row.id},
                    )
                updated += 1
            except Exception as e:
                logger.debug(f"RuleLifecycle: embedding rule {row.id} failed (non-blocking): {e}")
        return updated

    async def gate_candidate_rules(self, user_id: Optional[str] = None) -> Dict[str, int]:
        """
        Gate all candidate rules for a user.
        If a rule passes/fails/becomes provisional, we update database and regenerate STATE.md.
        """
        import json
        uid = user_id or self.user_id
        stats = {"checked": 0, "passed": 0, "provisional": 0, "rejected": 0, "failed": 0}
        
        try:
            with self._engine().connect() as conn:
                rows = conn.execute(
                    text("""
                        SELECT id, agent_name, rule_text, source_decision_id, created_at
                        FROM agent_rules
                        WHERE user_id = :uid AND status = 'candidate'
                    """),
                    {"uid": uid}
                ).fetchall()
        except Exception as e:
            logger.error(f"RuleLifecycle: failed to query candidate rules: {e}")
            return stats

        for row in rows:
            rule_id = row.id
            agent_name = row.agent_name
            rule_text = row.rule_text
            source_decision_id = row.source_decision_id
            created_at = row.created_at
            
            stats["checked"] += 1
            
            # Check 14-day safety valve
            now = datetime.now(timezone.utc) if created_at.tzinfo else datetime.now()
            if created_at < now - timedelta(days=14):
                try:
                    with self._engine().begin() as conn:
                        conn.execute(
                            text("""
                                UPDATE agent_rules
                                SET status = 'active', gate_status = 'provisional',
                                    expires_at = NOW() + INTERVAL '30 days',
                                    gate_checked_at = NOW(),
                                    gate_details = :details,
                                    updated_at = NOW()
                                WHERE id = :rid
                            """),
                            {
                                "rid": rule_id,
                                "details": '{"reason": "14-day safety valve auto-promotion", "provisional": true}'
                            }
                        )
                    stats["provisional"] += 1
                    logger.info(f"RuleLifecycle: rule {rule_id} auto-promoted to provisional (14-day safety valve)")
                    self._refresh_file_cache(agent_name, uid)
                except Exception as e:
                    logger.error(f"RuleLifecycle: failed auto-promotion of rule {rule_id}: {e}")
                    stats["failed"] += 1
                continue
                
            # Run gate evaluation
            try:
                verdict, details = await self._gate_one(uid, rule_id, agent_name, rule_text, source_decision_id)
                if verdict == "passed":
                    with self._engine().begin() as conn:
                        conn.execute(
                            text("""
                                UPDATE agent_rules
                                SET status = 'active', gate_status = 'passed',
                                    gate_checked_at = NOW(),
                                    gate_details = CAST(:details AS jsonb),
                                    updated_at = NOW()
                                WHERE id = :rid
                            """),
                            {"rid": rule_id, "details": json.dumps(details)}
                        )
                    stats["passed"] += 1
                    logger.info(f"RuleLifecycle: rule {rule_id} passed gate -> active")
                    self._refresh_file_cache(agent_name, uid)
                elif verdict == "provisional":
                    with self._engine().begin() as conn:
                        conn.execute(
                            text("""
                                UPDATE agent_rules
                                SET status = 'active', gate_status = 'provisional',
                                    expires_at = NOW() + INTERVAL '30 days',
                                    gate_checked_at = NOW(),
                                    gate_details = CAST(:details AS jsonb),
                                    updated_at = NOW()
                                WHERE id = :rid
                            """),
                            {"rid": rule_id, "details": json.dumps(details)}
                        )
                    stats["provisional"] += 1
                    logger.info(f"RuleLifecycle: rule {rule_id} provisional -> active (30d TTL)")
                    self._refresh_file_cache(agent_name, uid)
                elif verdict == "rejected":
                    with self._engine().begin() as conn:
                        conn.execute(
                            text("""
                                UPDATE agent_rules
                                SET status = 'rejected', gate_status = 'rejected',
                                    gate_checked_at = NOW(),
                                    gate_details = CAST(:details AS jsonb),
                                    updated_at = NOW()
                                WHERE id = :rid
                            """),
                            {"rid": rule_id, "details": json.dumps(details)}
                        )
                    stats["rejected"] += 1
                    logger.info(f"RuleLifecycle: rule {rule_id} rejected -> archived")
                else:
                    stats["failed"] += 1
            except Exception as e:
                logger.error(f"RuleLifecycle: gating rule {rule_id} failed: {e}", exc_info=True)
                stats["failed"] += 1
                
        return stats

    async def _gate_one(
        self, user_id: str, rule_id: int, agent_name: str, rule_text: str, source_decision_id: Optional[str]
    ) -> Tuple[str, Dict[str, Any]]:
        import json
        exclude_id = source_decision_id or "NONE"
        
        try:
            with self._engine().connect() as conn:
                rows = conn.execute(
                    text("""
                        SELECT id, agent_name, ticker, signal, alpha_pct, lesson
                        FROM decision_outcomes
                        WHERE user_id = :uid
                          AND id != :exclude_id
                          AND resolved_at IS NOT NULL
                          AND alpha_pct IS NOT NULL
                        ORDER BY CASE WHEN agent_name = :agent_name THEN 1 ELSE 0 END DESC, resolved_at DESC
                        LIMIT :limit
                    """),
                    {"uid": user_id, "exclude_id": exclude_id, "agent_name": agent_name, "limit": GATE_SAMPLE_LIMIT}
                ).fetchall()
        except Exception as e:
            logger.error(f"RuleLifecycle: DB read failed in _gate_one: {e}")
            raise e
            
        decisions = [
            {
                "id": r.id,
                "agent_name": r.agent_name,
                "ticker": r.ticker,
                "signal": r.signal,
                "alpha_pct": float(r.alpha_pct),
                "lesson": r.lesson or ""
            }
            for r in rows
        ]
        
        if not decisions:
            return "provisional", {
                "matched_ids": [],
                "sample_size": 0,
                "mean_alpha": None,
                "threshold": GATE_PASS_ALPHA_CEILING,
                "reason": "No historical decisions available"
            }
            
        try:
            from src.agents.structured import invoke_structured
            from src.infrastructure.llm.llm_config_chain import build_config_chain
            from src.infrastructure.llm.resilient_pipeline import ResilientLLMPipeline
            from src.domain.interfaces import Message
            from pydantic import BaseModel, Field

            class _MatchedDecisions(BaseModel):
                matched_decision_ids: List[str] = Field(default_factory=list)

            chain = build_config_chain(user_id, "nano")
            if not chain:
                raise ValueError("No LLM config chain available")
                
            pipeline = ResilientLLMPipeline(
                config_chain=chain, user_id=user_id,
                agent_name="RuleGateJudge", tier="nano"
            )
            gateway = pipeline._gateway_factory(chain[0])
            config = pipeline._build_llm_config(chain[0], temperature=0.0, max_tokens=250)
            
            decisions_listing = "\n".join(
                f"[{d['id']}] Agent: {d['agent_name']}, Ticker: {d['ticker']}, Signal: {d['signal']}, Lesson: {d['lesson']}"
                for d in decisions
            )
            
            prompt = (
                f"We are evaluating a candidate trading rule to see if it would have matched/applied to past decisions.\n\n"
                f"Candidate Rule: {rule_text}\n\n"
                f"Past Decisions:\n{decisions_listing}\n\n"
                "Please identify the IDs of all past decisions where this candidate rule would have been relevant and active (i.e. the rule's condition is met by the decision context/lesson). "
                "Return only the matched decision IDs in the list. If none apply, return an empty list."
            )
            
            parsed, _raw = await invoke_structured(
                gateway, [Message(role="user", content=prompt)], config, _MatchedDecisions
            )
            matched_ids = parsed.matched_decision_ids if parsed else []
        except Exception as e:
            logger.error(f"RuleLifecycle: LLM gate evaluation failed for rule {rule_id}: {e}")
            raise e
            
        valid_decision_ids = {d["id"] for d in decisions}
        matched_ids = [mid for mid in matched_ids if mid in valid_decision_ids]
        
        matched_count = len(matched_ids)
        if matched_count < GATE_MIN_MATCHES:
            return "provisional", {
                "matched_ids": matched_ids,
                "sample_size": len(decisions),
                "mean_alpha": None,
                "threshold": GATE_PASS_ALPHA_CEILING,
                "reason": f"Insufficient matches ({matched_count} < {GATE_MIN_MATCHES})"
            }
            
        alphas = [d["alpha_pct"] for d in decisions if d["id"] in matched_ids]
        mean_alpha = sum(alphas) / len(alphas)
        
        if mean_alpha <= GATE_PASS_ALPHA_CEILING:
            return "passed", {
                "matched_ids": matched_ids,
                "sample_size": len(decisions),
                "mean_alpha": round(mean_alpha, 4),
                "threshold": GATE_PASS_ALPHA_CEILING,
                "reason": f"Mean alpha {mean_alpha:.4f}% <= {GATE_PASS_ALPHA_CEILING}% threshold"
            }
        else:
            return "rejected", {
                "matched_ids": matched_ids,
                "sample_size": len(decisions),
                "mean_alpha": round(mean_alpha, 4),
                "threshold": GATE_PASS_ALPHA_CEILING,
                "reason": f"Mean alpha {mean_alpha:.4f}% > {GATE_PASS_ALPHA_CEILING}% threshold"
            }

    def _refresh_file_cache(self, agent_name: str, user_id: str):
        try:
            from src.repositories.memory_repository import AgentState
            agent_state = AgentState()
            agent_state._save_to_file(agent_name, agent_state.load_general_rules(agent_name, user_id=user_id))
        except Exception as e:
            logger.warning(f"RuleLifecycle: failed to refresh file cache for {agent_name}: {e}")
