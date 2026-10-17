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
        # Generic detail: the cause is in the log above, never echoed to the client (CodeQL py/stack-trace-exposure).
        # 對外只回通用訊息；原因已記錄在上方日誌。
        raise HTTPException(status_code=500, detail="Mission API request failed")


@router.get("/parking-plan")
async def get_parking_plan(user_id: str = Depends(get_current_user_id)) -> Dict[str, Any]:
    """Dry-run preview of benchmark parking: what it would buy today. Never places an order.
    基準停泊的乾跑預覽：今天會買多少；絕不下單。"""
    try:
        from src.services.benchmark_parking_service import BenchmarkParkingService

        return {"status": "success", "data": await BenchmarkParkingService(user_id=user_id).build_plan()}
    except Exception as e:
        logger.error(f"get_parking_plan failed: {e}", exc_info=True)
        # Generic detail: the cause is in the log above, never echoed to the client (CodeQL py/stack-trace-exposure).
        # 對外只回通用訊息；原因已記錄在上方日誌。
        raise HTTPException(status_code=500, detail="Mission API request failed")


@router.get("/strategies")
async def get_strategy_trials(user_id: str = Depends(get_current_user_id)) -> Dict[str, Any]:
    """Every strategy variant ever evaluated (the multiple-testing ledger) and its verdict.
    所有評估過的策略變體（多重檢定帳本）及其判定。"""
    try:
        from src.services.strategy_lab_service import StrategyLabService

        lab = StrategyLabService()
        return {"status": "success", "data": {"n_trials_total": lab.trial_count(), "trials": lab.list_trials()}}
    except Exception as e:
        logger.error(f"get_strategy_trials failed: {e}", exc_info=True)
        # Generic detail: the cause is in the log above, never echoed to the client (CodeQL py/stack-trace-exposure).
        # 對外只回通用訊息；原因已記錄在上方日誌。
        raise HTTPException(status_code=500, detail="Mission API request failed")
