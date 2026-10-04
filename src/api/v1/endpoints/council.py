"""
Council decision-transparency API (P5.2, 2026-07-11) — list + fetch council
session minutes (topic, consensus, full agent-by-agent transcript including
the P3.1 Risk Challenge round). Powers the "Decisions" transparency view —
this is the advisor's differentiator vs. reference systems (TradingAgents,
freqtrade): most systems show a final signal; this shows HOW the council
argued its way there.
"""
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, Request
from src.api.v1.dependencies import get_current_user_id
from src.api.v1.schemas.council_blindspot_schemas import (
    BlindspotListResponse,
    BlindspotResolveRequest,
    BlindspotResolveResponse,
    BlindspotScanResponse,
    BlindspotSchema,
)
from src.api.v1.schemas.council_memory_schemas import (
    CouncilMemoryDetailResponse,
    CouncilMemorySearchRequest,
    CouncilMemorySearchResponse,
    DebateOutcomeSchema,
    DebatePrecedentSchema,
)
from src.api.v1.schemas.council_meta_learning_schemas import (
    AgentAttributionSchema,
    MetaLearningAttributionsResponse,
    MetaLearningStatusResponse,
)
from src.repositories.vector_repository import AlchemyVectorRepository
from src.services.adaptive_council_meta_learning_service import AdaptiveCouncilMetaLearningService
from src.services.cognitive_blindspot_service import CognitiveBlindspotService
from src.services.council_debate_memory_service import CouncilDebateMemoryService
from src.utils.logger import setup_logger
from src.utils.rate_limit import limiter

logger = setup_logger("API_Council")
router = APIRouter()


def get_vector_repo() -> AlchemyVectorRepository:
    return AlchemyVectorRepository()


def get_meta_learning_service(user_id: str = Depends(get_current_user_id)) -> AdaptiveCouncilMetaLearningService:
    return AdaptiveCouncilMetaLearningService(user_id=user_id)


def get_blindspot_service(user_id: str = Depends(get_current_user_id)) -> CognitiveBlindspotService:
    return CognitiveBlindspotService(user_id=user_id)


def get_debate_memory_service(user_id: str = Depends(get_current_user_id)) -> CouncilDebateMemoryService:
    return CouncilDebateMemoryService(user_id=user_id)


@router.get("/sessions")
@limiter.limit("10/minute")
async def list_sessions(
    request: Request,
    limit: int = 20,
    user_id: str = Depends(get_current_user_id),
    repo: AlchemyVectorRepository = Depends(get_vector_repo),
) -> Dict[str, Any]:
    """List recent council sessions (topic + consensus preview), newest first."""
    try:
        minutes = repo.list_minutes(user_id=user_id, limit=limit)
        return {"status": "success", "sessions": minutes}
    except Exception as e:
        logger.error(f"list_sessions failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/sessions/{minute_id}")
@limiter.limit("10/minute")
async def get_session(
    request: Request,
    minute_id: str,
    user_id: str = Depends(get_current_user_id),
    repo: AlchemyVectorRepository = Depends(get_vector_repo),
) -> Dict[str, Any]:
    """
    Fetch a single council session in full: topic, final consensus, and the
    complete agent-by-agent transcript (each agent's stance, plus the Risk
    Challenge round if one occurred).
    """
    minute = repo.get_minute(minute_id)
    if not minute or minute.get("user_id") != user_id:
        raise HTTPException(status_code=404, detail="Council session not found")

    # transcript is stored as a single text blob (agents joined by newline in
    # council_service); split back into per-agent entries for the UI.
    raw_transcript = minute.get("transcript") or ""
    entries = [line for line in raw_transcript.split("\n") if line.strip()]

    return {"status": "success", "session": {**minute, "transcript_entries": entries}}


@router.get("/meta-learning/status", response_model=MetaLearningStatusResponse)
@limiter.limit("20/minute")
async def get_meta_learning_status(
    request: Request,
    user_id: str = Depends(get_current_user_id),
    service: AdaptiveCouncilMetaLearningService = Depends(get_meta_learning_service),
) -> MetaLearningStatusResponse:
    """Fetch current regime, tail risk metrics, and calibrated meta-weights."""
    try:
        ctx = service.generate_adaptive_council_context()
        return MetaLearningStatusResponse(
            status="success",
            current_regime=ctx.current_regime,
            regime_confidence=ctx.regime_confidence,
            black_swan_alert_level=ctx.black_swan_alert_level,
            var_999=ctx.var_999,
            cvar_999=ctx.cvar_999,
            fat_tail_ratio=ctx.fat_tail_ratio,
            health_score=ctx.health_score,
            health_rating=ctx.health_rating,
            target_cash_buffer=ctx.target_cash_buffer,
            target_beta=ctx.target_beta,
            meta_weights=ctx.meta_weights,
            prompt_guidance=ctx.prompt_guidance,
            veto_power_active=ctx.veto_power_active,
        )
    except Exception as e:
        logger.error(f"get_meta_learning_status failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/meta-learning/attributions", response_model=MetaLearningAttributionsResponse)
@limiter.limit("20/minute")
async def get_meta_learning_attributions(
    request: Request,
    user_id: str = Depends(get_current_user_id),
    service: AdaptiveCouncilMetaLearningService = Depends(get_meta_learning_service),
) -> MetaLearningAttributionsResponse:
    """Fetch expert agents historical outcome attributions and rolling win rates."""
    try:
        attrs = service.compute_agent_attributions()
        return MetaLearningAttributionsResponse(
            status="success",
            attributions={
                name: AgentAttributionSchema(
                    agent_name=attr.agent_name,
                    total_calls=attr.total_calls,
                    correct_calls=attr.correct_calls,
                    rolling_win_rate=attr.rolling_win_rate,
                    avg_alpha_contribution=attr.avg_alpha_contribution,
                    regime_win_rates=attr.regime_win_rates,
                )
                for name, attr in attrs.items()
            },
        )
    except Exception as e:
        logger.error(f"get_meta_learning_attributions failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/meta-learning/calibrate", response_model=MetaLearningStatusResponse)
@limiter.limit("10/minute")
async def calibrate_meta_learning(
    request: Request,
    user_id: str = Depends(get_current_user_id),
    service: AdaptiveCouncilMetaLearningService = Depends(get_meta_learning_service),
) -> MetaLearningStatusResponse:
    """Trigger on-demand calibration of expert meta-weights and prior context."""
    try:
        ctx = service.generate_adaptive_council_context()
        return MetaLearningStatusResponse(
            status="success",
            current_regime=ctx.current_regime,
            regime_confidence=ctx.regime_confidence,
            black_swan_alert_level=ctx.black_swan_alert_level,
            var_999=ctx.var_999,
            cvar_999=ctx.cvar_999,
            fat_tail_ratio=ctx.fat_tail_ratio,
            health_score=ctx.health_score,
            health_rating=ctx.health_rating,
            target_cash_buffer=ctx.target_cash_buffer,
            target_beta=ctx.target_beta,
            meta_weights=ctx.meta_weights,
            prompt_guidance=ctx.prompt_guidance,
            veto_power_active=ctx.veto_power_active,
        )
    except Exception as e:
        logger.error(f"calibrate_meta_learning failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ── A2: Cognitive Blindspot Detector Endpoints ───────────────────────────────

@router.get("/blindspots", response_model=BlindspotListResponse)
@limiter.limit("20/minute")
async def list_blindspots(
    request: Request,
    user_id: str = Depends(get_current_user_id),
    service: CognitiveBlindspotService = Depends(get_blindspot_service),
) -> BlindspotListResponse:
    """Fetch all active cognitive blindspots and reflection constraints."""
    try:
        active = service.get_active_blindspots()
        return BlindspotListResponse(
            status="success",
            total_active=len(active),
            blindspots=[
                BlindspotSchema(
                    id=b.id,
                    user_id=b.user_id,
                    agent_name=b.agent_name,
                    bias_pattern=b.bias_pattern,
                    regime=b.regime,
                    consecutive_failures=b.consecutive_failures,
                    avg_alpha_loss=float(b.avg_alpha_loss or 0.0),
                    severity=b.severity,
                    corrective_guidance=b.corrective_guidance,
                    is_active=b.is_active,
                    detected_at=b.detected_at,
                    resolved_at=b.resolved_at,
                )
                for b in active
            ],
        )
    except Exception as e:
        logger.error(f"list_blindspots failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/blindspots/scan", response_model=BlindspotScanResponse)
@limiter.limit("10/minute")
async def scan_blindspots(
    request: Request,
    regime: str = "SIDEWAYS_HIGH_VOL",
    user_id: str = Depends(get_current_user_id),
    service: CognitiveBlindspotService = Depends(get_blindspot_service),
) -> BlindspotScanResponse:
    """Trigger on-demand scan of agent cognitive blindspots across historical outcomes."""
    try:
        detected = service.scan_and_detect_blindspots(current_regime=regime)
        active = service.get_active_blindspots()
        return BlindspotScanResponse(
            status="success",
            scanned_agents=5,
            new_blindspots_detected=len(detected),
            active_blindspots=[
                BlindspotSchema(
                    id=b.id,
                    user_id=b.user_id,
                    agent_name=b.agent_name,
                    bias_pattern=b.bias_pattern,
                    regime=b.regime,
                    consecutive_failures=b.consecutive_failures,
                    avg_alpha_loss=float(b.avg_alpha_loss or 0.0),
                    severity=b.severity,
                    corrective_guidance=b.corrective_guidance,
                    is_active=b.is_active,
                    detected_at=b.detected_at,
                    resolved_at=b.resolved_at,
                )
                for b in active
            ],
        )
    except Exception as e:
        logger.error(f"scan_blindspots failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/blindspots/{blindspot_id}/resolve", response_model=BlindspotResolveResponse)
@limiter.limit("20/minute")
async def resolve_blindspot(
    request: Request,
    blindspot_id: str,
    body: BlindspotResolveRequest = BlindspotResolveRequest(),
    user_id: str = Depends(get_current_user_id),
    service: CognitiveBlindspotService = Depends(get_blindspot_service),
) -> BlindspotResolveResponse:
    """Manually resolve and calibrate an active cognitive blindspot constraint."""
    try:
        success = service.resolve_blindspot(blindspot_id)
        if not success:
            raise HTTPException(status_code=404, detail="Blindspot not found or already resolved.")
        from datetime import datetime, timezone
        return BlindspotResolveResponse(
            status="success",
            blindspot_id=blindspot_id,
            resolved_at=datetime.now(timezone.utc),
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"resolve_blindspot failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/memory/search", response_model=CouncilMemorySearchResponse)
@limiter.limit("20/minute")
async def search_council_memory(
    request: Request,
    body: CouncilMemorySearchRequest,
    user_id: str = Depends(get_current_user_id),
    service: CouncilDebateMemoryService = Depends(get_debate_memory_service),
) -> CouncilMemorySearchResponse:
    """
    Search historical council debate precedents using vector similarity + outcome attribution re-ranking (A3).
    """
    try:
        precedents = service.search_debates_api(
            query=body.query,
            ticker=body.ticker,
            min_alpha=body.min_alpha,
            limit=body.limit,
        )
        prompt_block = service.synthesize_precedents_for_prompt(precedents)
        return CouncilMemorySearchResponse(
            status="success",
            query=body.query,
            total_found=len(precedents),
            synthesized_prompt_context=prompt_block,
            precedents=[
                DebatePrecedentSchema(
                    minute_id=p.minute_id,
                    session_id=p.session_id,
                    topic=p.topic,
                    consensus=p.consensus,
                    created_at=p.created_at,
                    similarity=p.similarity,
                    relevance_score=p.relevance_score,
                    has_attribution=p.has_attribution,
                    avg_alpha_pct=p.avg_alpha_pct,
                    outcomes=[
                        DebateOutcomeSchema(
                            outcome_id=o.outcome_id,
                            ticker=o.ticker,
                            agent_name=o.agent_name,
                            signal=o.signal,
                            realized_return_pct=o.realized_return_pct,
                            benchmark_return_pct=o.benchmark_return_pct,
                            alpha_pct=o.alpha_pct,
                            lesson=o.lesson,
                            resolved_at=o.resolved_at,
                        )
                        for o in p.outcomes
                    ],
                    participants=p.participants,
                    transcript_preview=p.transcript_preview,
                )
                for p in precedents
            ],
        )
    except Exception as e:
        logger.error(f"search_council_memory failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/memory/{session_id}", response_model=CouncilMemoryDetailResponse)
@limiter.limit("20/minute")
async def get_council_memory_detail(
    request: Request,
    session_id: str,
    user_id: str = Depends(get_current_user_id),
    service: CouncilDebateMemoryService = Depends(get_debate_memory_service),
) -> CouncilMemoryDetailResponse:
    """
    Fetch comprehensive debate memory detail including consensus, transcript, and associated decision outcomes (A3).
    """
    try:
        detail = service.get_debate_detail(session_id)
        if not detail or detail.get("user_id") != user_id:
            raise HTTPException(status_code=404, detail="Debate memory session not found")
        return CouncilMemoryDetailResponse(
            status="success",
            minute_id=detail["minute_id"],
            session_id=detail["session_id"],
            user_id=detail["user_id"],
            topic=detail["topic"],
            participants=detail.get("participants"),
            consensus=detail.get("consensus"),
            transcript=detail.get("transcript"),
            created_at=detail.get("created_at"),
            outcomes=[
                DebateOutcomeSchema(
                    outcome_id=o["outcome_id"],
                    ticker=o["ticker"],
                    agent_name=o["agent_name"],
                    signal=o["signal"],
                    realized_return_pct=o.get("realized_return_pct"),
                    benchmark_return_pct=o.get("benchmark_return_pct"),
                    alpha_pct=o.get("alpha_pct"),
                    lesson=o.get("lesson"),
                    resolved_at=o.get("resolved_at"),
                )
                for o in detail.get("outcomes", [])
            ],
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"get_council_memory_detail failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))



