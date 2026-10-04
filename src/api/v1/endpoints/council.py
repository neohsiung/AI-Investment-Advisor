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
from src.api.v1.schemas.council_meta_learning_schemas import (
    AgentAttributionSchema,
    MetaLearningAttributionsResponse,
    MetaLearningStatusResponse,
)
from src.repositories.vector_repository import AlchemyVectorRepository
from src.services.adaptive_council_meta_learning_service import AdaptiveCouncilMetaLearningService
from src.utils.logger import setup_logger
from src.utils.rate_limit import limiter

logger = setup_logger("API_Council")
router = APIRouter()


def get_vector_repo() -> AlchemyVectorRepository:
    return AlchemyVectorRepository()


def get_meta_learning_service(user_id: str = Depends(get_current_user_id)) -> AdaptiveCouncilMetaLearningService:
    return AdaptiveCouncilMetaLearningService(user_id=user_id)


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

