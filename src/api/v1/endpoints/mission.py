"""
Mission status API — kill-criteria watchdog + the mission file version. 0-LLM, read-only.
使命狀態 API — kill criteria 看門狗與使命檔版本；0-LLM、唯讀。
"""
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException

from src.api.v1.dependencies import get_current_user_id
from src.utils.logger import setup_logger

logger = setup_logger("API_Mission")
router = APIRouter()


@router.get("/status")
async def get_mission_status(user_id: str = Depends(get_current_user_id)) -> Dict[str, Any]:
    try:
        from src.services.mission_watchdog_service import MissionWatchdogService

        return {"status": "success", "data": MissionWatchdogService(user_id=user_id).evaluate()}
    except Exception as e:
        logger.error(f"get_mission_status failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
