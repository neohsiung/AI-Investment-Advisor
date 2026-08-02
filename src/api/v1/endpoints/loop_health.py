"""
Loop health API (B-P3.2, 2026-07-14) — one endpoint aggregating metrics
from all three self-improvement loops (investment learning, self-ops,
user feedback) for the /health dashboard page. Pure SQL, zero LLM cost.
"""
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text

from src.api.v1.router import get_current_user_id
from src.data.database import get_db_engine
from src.utils.logger import setup_logger

logger = setup_logger("API_LoopHealth")
router = APIRouter()


@router.get("")
async def get_loop_health(user_id: str = Depends(get_current_user_id)) -> Dict[str, Any]:
    """
    Snapshot across all three loops:
      - learning: decision resolution rate, rule counts by status, avg score
      - self_ops: dead-man breaches this week, remediation actions by tier
      - feedback: approval rate, rejection-reason capture rate, preference sample size
      - caching: total_workflow_runs, cache_hits, cache_misses, saved_cost_usd
    """
    try:
        engine = get_db_engine()
        with engine.connect() as conn:
            learning = _learning_metrics(conn, user_id)
            self_ops = _self_ops_metrics(conn, user_id)
            feedback = _feedback_metrics(conn, user_id)
            
        # Retrieve caching telemetry
        from src.infrastructure.workflow.cache import WorkflowCache
        cache = WorkflowCache()
        caching = await cache.get_all_telemetry()
        
        return {
            "status": "success",
            "learning": learning,
            "self_ops": self_ops,
            "feedback": feedback,
            "caching": caching
        }
    except Exception as e:
        logger.error(f"get_loop_health failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


def _learning_metrics(conn, user_id: str) -> Dict[str, Any]:
    decisions = conn.execute(
        text("""
            SELECT
                COUNT(*) AS total,
                COUNT(*) FILTER (WHERE resolved_at IS NOT NULL) AS resolved
            FROM decision_outcomes WHERE user_id = :uid
        """),
        {"uid": user_id},
    ).fetchone()

    rule_rows = conn.execute(
        text("""
            SELECT status, COUNT(*) AS n, AVG(score) AS avg_score
            FROM agent_rules WHERE user_id = :uid GROUP BY status
        """),
        {"uid": user_id},
    ).fetchall()
    rules_by_status = {r.status: r.n for r in rule_rows}
    avg_active_score = next((float(r.avg_score) for r in rule_rows if r.status == "active" and r.avg_score is not None), None)

    total = decisions.total or 0
    resolved = decisions.resolved or 0
    return {
        "decisions_total": total,
        "decisions_resolved": resolved,
        "resolution_rate": round(resolved / total, 3) if total else None,
        "rules_by_status": rules_by_status,
        "avg_active_rule_score": round(avg_active_score, 3) if avg_active_score is not None else None,
    }


def _self_ops_metrics(conn, user_id: str) -> Dict[str, Any]:
    breaches = conn.execute(
        text("""
            SELECT COUNT(*) FROM expected_outcomes
            WHERE last_alerted_at > NOW() - INTERVAL '7 days'
        """)
    ).fetchone()[0]

    remediation_rows = conn.execute(
        text("""
            SELECT tier, COUNT(*) AS n FROM remediation_log
            WHERE created_at > NOW() - INTERVAL '7 days'
            GROUP BY tier
        """)
    ).fetchall()
    remediation_by_tier = {r.tier: r.n for r in remediation_rows}

    cost_row = conn.execute(
        text("""
            SELECT COALESCE(SUM(total_cost_usd), 0) FROM llm_usage_logs
            WHERE user_id = :uid AND timestamp > NOW() - INTERVAL '7 days'
        """),
        {"uid": user_id},
    ).fetchone()
    weekly_cost = float(cost_row[0] or 0)

    return {
        "breaches_this_week": breaches,
        "remediation_by_tier": remediation_by_tier,
        "weekly_cost_usd": round(weekly_cost, 2),
        "weekly_budget_usd": 30.0,
    }


def _feedback_metrics(conn, user_id: str) -> Dict[str, Any]:
    counts = conn.execute(
        text("""
            SELECT decision, COUNT(*) AS n FROM interaction_feedback
            WHERE user_id = :uid GROUP BY decision
        """),
        {"uid": user_id},
    ).fetchall()
    by_decision = {r.decision: r.n for r in counts}
    approved = by_decision.get("approved", 0)
    rejected = by_decision.get("rejected", 0)
    decided = approved + rejected

    reason_capture = conn.execute(
        text("""
            SELECT
                COUNT(*) FILTER (WHERE reason_code IS NOT NULL) AS with_reason,
                COUNT(*) AS total
            FROM interaction_feedback WHERE user_id = :uid AND decision = 'rejected'
        """),
        {"uid": user_id},
    ).fetchone()

    pref_row = conn.execute(
        text("SELECT sample_size, risk_appetite_score FROM user_preferences WHERE user_id = :uid"),
        {"uid": user_id},
    ).fetchone()

    return {
        "approval_rate": round(approved / decided, 3) if decided else None,
        "by_decision": by_decision,
        "rejection_reason_capture_rate": (
            round(reason_capture.with_reason / reason_capture.total, 3)
            if reason_capture.total else None
        ),
        "preference_sample_size": pref_row.sample_size if pref_row else 0,
        "risk_appetite_score": float(pref_row.risk_appetite_score) if pref_row and pref_row.risk_appetite_score is not None else None,
    }
