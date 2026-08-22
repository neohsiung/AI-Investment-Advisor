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
from src.api.v1.router import get_current_user_id
from src.repositories.vector_repository import AlchemyVectorRepository
from src.utils.logger import setup_logger
from src.utils.rate_limit import limiter

logger = setup_logger("API_Council")
router = APIRouter()


def get_vector_repo() -> AlchemyVectorRepository:
    return AlchemyVectorRepository()


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
