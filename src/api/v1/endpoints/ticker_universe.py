"""Ticker Universe API endpoints."""
from fastapi import APIRouter, Depends, HTTPException, Query
from typing import Optional
from uuid import UUID
from datetime import datetime

from src.api.v1.schemas.ticker_universe_schemas import (
    TickerUniverseListResponse, TickerUniverseRecord,
    TickerUniverseAddRequest, TickerUniverseUpdateRequest,
    TickerUniverseRemoveRequest, ActionResponse, TickerInfoResponse,
    ResearchListResponse, ResearchSubmitRequest,
    TargetAllocationListResponse, TargetAllocationRecord,
    LogListResponse,
)
from src.services.ticker_universe_service import TickerUniverseService
from src.utils.logger import setup_logger

logger = setup_logger("API_TickerUniverse")
router = APIRouter()

from src.api.v1.dependencies import get_current_user_id


def _serialize(r: dict) -> dict:
    """Convert UUID/datetime to strings for Pydantic v2 compatibility."""
    result = {}
    for k, v in r.items():
        if isinstance(v, UUID):
            result[k] = str(v)
        elif isinstance(v, datetime):
            result[k] = v.isoformat()
        elif k in ("id", "user_id") and v is not None:
            result[k] = str(v) if not isinstance(v, str) else v
        else:
            result[k] = v
    return result


def get_service(user_id: str = Depends(get_current_user_id)) -> TickerUniverseService:
    return TickerUniverseService(user_id=user_id)


# ── Specific routes (must be before /{ticker} to avoid path conflicts) ──


@router.get("/targets/optimize", response_model=TickerInfoResponse)
async def optimize_targets(service: TickerUniverseService = Depends(get_service)):
    """重新計算目標配置（信心指數驅動優化）"""
    try:
        result = service.optimize_allocations()
        return {"status": "success" if result.get("success") else "error", "data": result}
    except Exception as e:
        logger.error(f"Optimize targets failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/targets", response_model=TargetAllocationListResponse)
async def get_targets(service: TickerUniverseService = Depends(get_service)):
    """獲取所有標的的目標配置"""
    try:
        data = service.get_targets()
        records = [_serialize(r) for r in data]
        return {"status": "success", "data": records}
    except Exception as e:
        logger.error(f"Error fetching targets: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/logs", response_model=LogListResponse)
async def get_logs(
    limit: int = Query(50, ge=1, le=500),
    service: TickerUniverseService = Depends(get_service),
):
    """獲取標的池操作日誌"""
    try:
        data = service.get_logs(limit)
        records = [_serialize(r) for r in data]
        return {"status": "success", "data": records}
    except Exception as e:
        logger.error(f"Error fetching logs: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/migrate", response_model=TickerInfoResponse)
async def migrate_holdings(service: TickerUniverseService = Depends(get_service)):
    """將現有持倉導入標的池（一次性）"""
    try:
        result = service.migrate_from_holdings()
        return {"status": "success", "data": result}
    except Exception as e:
        logger.error(f"Migration failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/research/run", response_model=TickerInfoResponse)
async def run_batch_research(service: TickerUniverseService = Depends(get_service)):
    """對所有活躍標的執行 LLM 研究週期"""
    try:
        from src.services.research_automation_service import ResearchAutomationService
        svc = ResearchAutomationService(user_id=service.user_id)
        result = await svc.run_weekly_research(parallel=3)
        count = result.get("researched", 0)
        total = result.get("total", 0)
        errors = result.get("errors", 0)
        candidates = result.get("removal_candidates", [])
        return {"status": "success", "data": result,
                "message": f"Researched {count}/{total} tickers, {errors} errors, {len(candidates)} removal candidates"}
    except Exception as e:
        logger.error(f"Batch research failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/research/run/{ticker}", response_model=TickerInfoResponse)
async def run_single_research(ticker: str, service: TickerUniverseService = Depends(get_service)):
    """對單一標的執行 LLM 研究"""
    try:
        from src.services.research_automation_service import ResearchAutomationService
        svc = ResearchAutomationService(user_id=service.user_id)
        result = await svc.run_ticker_research(ticker.upper())
        return {"status": "success", "data": result}
    except Exception as e:
        logger.error(f"Research failed for {ticker}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/removal-candidates", response_model=TickerInfoResponse)
async def get_removal_candidates(service: TickerUniverseService = Depends(get_service)):
    """取得建議剔除的標的候選清單"""
    try:
        from src.services.research_automation_service import ResearchAutomationService
        svc = ResearchAutomationService(user_id=service.user_id)
        result = await svc.evaluate_removals()
        return {"status": "success", "data": result}
    except Exception as e:
        logger.error(f"Removal evaluation failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/rebalance/plan", response_model=TickerInfoResponse)
async def get_rebalance_plan(service: TickerUniverseService = Depends(get_service)):
    """計算再平衡計劃：信心目標 vs 當前倉位，產生買賣計劃（不執行）"""
    try:
        from src.services.confidence_rebalance_service import ConfidenceRebalanceService
        rbs = ConfidenceRebalanceService(user_id=service.user_id)
        plan = await rbs.get_rebalance_plan()
        return {"status": "success" if plan.get("success") else "error", "data": plan}
    except Exception as e:
        logger.error(f"Rebalance plan failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/rebalance", response_model=TickerInfoResponse)
async def execute_confidence_rebalance(service: TickerUniverseService = Depends(get_service)):
    """執行信心指數驅動的再平衡"""
    try:
        from src.services.confidence_rebalance_service import ConfidenceRebalanceService
        rbs = ConfidenceRebalanceService(user_id=service.user_id)
        result = await rbs.execute_rebalance()
        return {"status": "success" if result.get("success") else "error", "data": result}
    except Exception as e:
        logger.error(f"Rebalance execution failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ── Ticker Universe CRUD (must be after specific routes) ──


@router.get("", response_model=TickerUniverseListResponse)
async def get_universe(
    status: Optional[str] = Query(None, description="Filter by status: active, watch, removed"),
    service: TickerUniverseService = Depends(get_service),
):
    """獲取標的池列表"""
    try:
        data = service.get_universe(status)
        records = [TickerUniverseRecord.model_validate(_serialize(r)) for r in data]
        return {"status": "success", "data": records}
    except Exception as e:
        logger.error(f"Error fetching universe: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("", response_model=ActionResponse)
async def add_ticker(
    payload: TickerUniverseAddRequest,
    service: TickerUniverseService = Depends(get_service),
):
    """加入新標的到標的池"""
    try:
        result = service.add_ticker(**payload.model_dump())
        if not result["success"]:
            raise HTTPException(status_code=500, detail=result["message"])
        return {"status": "success", "message": result["message"]}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error adding ticker: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{ticker}", response_model=TickerInfoResponse)
async def get_ticker(
    ticker: str,
    service: TickerUniverseService = Depends(get_service),
):
    """獲取單一標的資訊"""
    try:
        data = service.get_by_ticker(ticker.upper())
        if not data:
            raise HTTPException(status_code=404, detail=f"{ticker} not found in universe")
        return {"status": "success", "data": data}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching {ticker}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.patch("/{ticker}", response_model=ActionResponse)
async def update_ticker(
    ticker: str,
    payload: TickerUniverseUpdateRequest,
    service: TickerUniverseService = Depends(get_service),
):
    """更新標的資訊（company_name, sector, industry, status）"""
    try:
        kwargs = payload.model_dump(exclude_none=True)
        result = service.update_ticker(ticker.upper(), **kwargs)
        if not result["success"]:
            raise HTTPException(status_code=400, detail=result["message"])
        return {"status": "success", "message": result["message"]}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating {ticker}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{ticker}", response_model=ActionResponse)
async def remove_ticker(
    ticker: str,
    payload: TickerUniverseRemoveRequest = TickerUniverseRemoveRequest(),
    service: TickerUniverseService = Depends(get_service),
):
    """軟刪除標的（設為 removed）"""
    try:
        result = service.remove_ticker(ticker.upper(), reason=payload.reason)
        if not result["success"]:
            raise HTTPException(status_code=500, detail=result["message"])
        return {"status": "success", "message": result["message"]}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error removing {ticker}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ── Research ──


@router.get("/{ticker}/research", response_model=ResearchListResponse)
async def get_research(
    ticker: str,
    limit: int = Query(10, ge=1, le=100),
    service: TickerUniverseService = Depends(get_service),
):
    """獲取指定標的研究報告"""
    try:
        data = service.get_research(ticker.upper(), limit)
        records = [_serialize(r) for r in data]
        return {"status": "success", "data": records}
    except Exception as e:
        logger.error(f"Error fetching research for {ticker}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/research", response_model=ActionResponse)
async def submit_research(
    payload: ResearchSubmitRequest,
    service: TickerUniverseService = Depends(get_service),
):
    """提交研究報告（Agent 調用）"""
    try:
        result = service.submit_research(**payload.model_dump())
        if not result["success"]:
            raise HTTPException(status_code=500, detail=result["message"])
        return {"status": "success", "message": result["message"]}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error submitting research: {e}")
        raise HTTPException(status_code=500, detail=str(e))