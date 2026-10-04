"""Ticker Universe API endpoints."""
from fastapi import APIRouter, Depends, HTTPException, Query
from typing import Optional
from pydantic import BaseModel
from uuid import UUID
from datetime import datetime

from src.api.v1.schemas.ticker_universe_schemas import (
    TickerUniverseListResponse, TickerUniverseRecord,
    TickerUniverseAddRequest, TickerUniverseUpdateRequest,
    TickerUniverseRemoveRequest, ActionResponse, TickerInfoResponse,
    ResearchListResponse, ResearchSubmitRequest,
    TargetAllocationListResponse, TargetAllocationRecord,
    LogListResponse, TickerPinRequest,
    PromotionPlanSchema, ShadowPromotionListResponse,
    ShadowPromotionExecuteRequest, ShadowPromotionExecuteResponse,
)
from src.services.ticker_universe_service import TickerUniverseService
from src.services.shadow_promotion_orchestrator import ShadowPromotionOrchestrator
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


def get_shadow_orchestrator(user_id: str = Depends(get_current_user_id)) -> ShadowPromotionOrchestrator:
    return ShadowPromotionOrchestrator(user_id=user_id)


# ── Specific routes (must be before /{ticker} to avoid path conflicts) ──


@router.get("/shadow/promotions", response_model=ShadowPromotionListResponse)
async def get_shadow_promotions(
    auto_execute: bool = Query(False, description="Automatically execute eligible rotations if configured"),
    orchestrator: ShadowPromotionOrchestrator = Depends(get_shadow_orchestrator),
):
    """
    評估影子候選標的之畢業考核狀態，並與實盤持倉進行機會成本換庫與 Alpha 鈍化對比 (P5)。
    """
    try:
        proposals = await orchestrator.evaluate_promotions(auto_execute_if_eligible=auto_execute)
        total_qual = sum(1 for p in proposals if p.qualified)
        total_rot = sum(1 for p in proposals if p.action_type == "CAPITAL_ROTATION")
        data = [PromotionPlanSchema(**p.to_dict()) for p in proposals]
        return ShadowPromotionListResponse(
            status="success",
            data=data,
            total_qualified=total_qual,
            total_rotations=total_rot,
        )
    except Exception as e:
        logger.error(f"Error evaluating shadow promotions: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error evaluating promotions")


@router.post("/shadow/promotions/execute", response_model=ShadowPromotionExecuteResponse)
async def execute_shadow_promotion(
    payload: ShadowPromotionExecuteRequest,
    orchestrator: ShadowPromotionOrchestrator = Depends(get_shadow_orchestrator),
):
    """
    執行指定影子標的之畢業提拔與實盤換庫置換（包含 E1 SOR 拆單排程與推播）(P5)。
    """
    try:
        res = await orchestrator.execute_promotion(
            candidate_ticker=payload.candidate_ticker,
            displaced_ticker=payload.displaced_ticker,
            auto_rebalance=payload.auto_rebalance,
        )
        if not res.success:
            raise HTTPException(status_code=400, detail=res.message)
        return ShadowPromotionExecuteResponse(
            status="success",
            data=res.to_dict(),
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error executing shadow promotion for {payload.candidate_ticker}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error executing promotion")


@router.get("/targets/optimize", response_model=TickerInfoResponse)
async def optimize_targets(service: TickerUniverseService = Depends(get_service)):
    """重新計算目標配置（信心指數驅動優化）"""
    try:
        result = service.optimize_allocations()
        return {"status": "success" if result.get("success") else "error", "data": result}
    except Exception as e:
        logger.error(f"Optimize targets failed: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/targets", response_model=TargetAllocationListResponse)
async def get_targets(service: TickerUniverseService = Depends(get_service)):
    """獲取所有標的的目標配置"""
    try:
        data = service.get_targets()
        records = [_serialize(r) for r in data]
        return {"status": "success", "data": records}
    except Exception as e:
        logger.error(f"Error fetching targets: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


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
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/migrate", response_model=TickerInfoResponse)
async def migrate_holdings(service: TickerUniverseService = Depends(get_service)):
    """將現有持倉導入標的池（一次性）"""
    try:
        result = await service.migrate_from_holdings()
        return {"status": "success", "data": result}
    except Exception as e:
        logger.error(f"Migration failed: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


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
        raise HTTPException(status_code=500, detail="Internal server error")


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
        raise HTTPException(status_code=500, detail="Internal server error")


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
        raise HTTPException(status_code=500, detail="Internal server error")


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
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/rebalance", response_model=TickerInfoResponse)
async def execute_confidence_rebalance(service: TickerUniverseService = Depends(get_service)):
    """執行信心指數驅動的再平衡"""
    try:
        from src.services.confidence_rebalance_service import ConfidenceRebalanceService
        rbs = ConfidenceRebalanceService(user_id=service.user_id)
        result = await rbs.execute_rebalance(enforce_market_hours=True)
        return {"status": "success" if result.get("success") else "error", "data": result}
    except Exception as e:
        logger.error(f"Rebalance execution failed: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


class ReclaimCapitalRequest(BaseModel):
    candidate_ticker: str
    target_amount: float
    candidate_score: Optional[float] = 8.5
    execute: Optional[bool] = False


@router.post("/rebalance/reclaim-capital", response_model=TickerInfoResponse)
async def reclaim_capital_endpoint(
    payload: ReclaimCapitalRequest,
    service: TickerUniverseService = Depends(get_service),
):
    """主動資本置換：計算或執行賣出低置信度/微型持倉，以籌措高置信度買入所需資金"""
    try:
        from src.services.confidence_rebalance_service import ConfidenceRebalanceService
        rbs = ConfidenceRebalanceService(user_id=service.user_id)
        result = await rbs.reclaim_capital_for_buy(
            candidate_ticker=payload.candidate_ticker.upper(),
            target_amount=payload.target_amount,
            candidate_score=payload.candidate_score or 8.5,
            execute=payload.execute or False,
        )
        return {"status": "success", "data": result}
    except Exception as e:
        logger.error(f"Reclaim capital failed: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")



@router.get("/quality-check/{ticker}", response_model=TickerInfoResponse)
async def check_ticker_quality(
    ticker: str,
    service: TickerUniverseService = Depends(get_service),
):
    """評估單一標的是否符合品質把關門檻（硬門檻、基本面、技術面、流動性）"""
    try:
        assessment = await service.evaluate_ticker_quality(ticker.upper())
        return {"status": "success", "data": assessment}
    except Exception as e:
        logger.error(f"Quality check failed for {ticker}: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/lifecycle/run", response_model=TickerInfoResponse)
async def run_lifecycle(
    force: bool = Query(False, description="Force run even if auto-refresh setting is false"),
    service: TickerUniverseService = Depends(get_service),
):
    """手動或定時觸發標的池生命週期演化（宏觀環境偵測、劣質剔除、優質納入）"""
    try:
        result = await service.run_lifecycle_evolution(force=force)
        return {"status": "success" if result.get("success") else "error", "data": result}
    except Exception as e:
        logger.error(f"Lifecycle run failed: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/pyramid-screen", response_model=TickerInfoResponse)
async def run_pyramid_screen_endpoint(
    top_n: int = Query(12, ge=3, le=50, description="Top candidates to retain from Stage 1"),
    auto_admit: bool = Query(False, description="Automatically admit Stage 2 approved candidates to universe"),
    service: TickerUniverseService = Depends(get_service),
):
    """執行兩階段金字塔初篩器：Stage 1 純量化快速篩選，Stage 2 深度品質把關"""
    try:
        result = await service.run_pyramid_screen(top_n=top_n, auto_admit=auto_admit)
        return {"status": "success", "data": result}
    except Exception as e:
        logger.error(f"Pyramid screen failed: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/candidates/evolve", response_model=TickerInfoResponse)
async def evolve_candidates_endpoint(
    max_candidates: Optional[int] = Query(None, ge=5, le=100, description="Max reserve candidates to retain"),
    service: TickerUniverseService = Depends(get_service),
):
    """手動觸發候選池動態演化與汰弱留強（收斂並留存 Top 30 儲備標的）"""
    try:
        result = await service.evolve_candidates(max_candidates=max_candidates)
        return {"status": "success", "data": result}
    except Exception as e:
        logger.error(f"Candidates evolution failed: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/active/evolve", response_model=TickerInfoResponse)
async def evolve_active_endpoint(
    max_active: Optional[int] = Query(None, ge=3, le=50, description="Max active tickers in universe"),
    rotation_hurdle: Optional[float] = Query(None, ge=0.5, le=5.0, description="Hurdle score delta required for candidate to replace active"),
    max_rotations: Optional[int] = Query(None, ge=1, le=5, description="Max active tickers rotated per cycle"),
    service: TickerUniverseService = Depends(get_service),
):
    """手動觸發活躍池動態汰弱留強（未鎖定之活躍股與候選股進行優勝劣汰輪換）"""
    try:
        result = await service.evolve_active(
            max_active=max_active,
            rotation_hurdle=rotation_hurdle,
            max_rotations=max_rotations,
        )
        return {"status": "success", "data": result}
    except Exception as e:
        logger.error(f"Active pool evolution failed: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


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
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("", response_model=ActionResponse)
async def add_ticker(
    payload: TickerUniverseAddRequest,
    service: TickerUniverseService = Depends(get_service),
):
    """加入新標的到標的池（預設進行嚴格品質檢查）"""
    try:
        data = payload.model_dump()
        result = await service.add_ticker_with_quality_gate(**data)
        if not result["success"]:
            raise HTTPException(status_code=400, detail=result["message"])
        return {"status": "success", "message": result["message"]}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error adding ticker: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


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
        raise HTTPException(status_code=500, detail="Internal server error")


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
        raise HTTPException(status_code=500, detail="Internal server error")


@router.put("/{ticker}/pin", response_model=ActionResponse)
async def pin_ticker_endpoint(
    ticker: str,
    payload: TickerPinRequest,
    service: TickerUniverseService = Depends(get_service),
):
    """設定標的指定/鎖定狀態（鎖定者免疫自動汰除與輪動）"""
    try:
        result = service.set_ticker_pin(ticker.upper(), payload.is_pinned)
        if not result["success"]:
            raise HTTPException(status_code=500, detail=result["message"])
        return {"status": "success", "message": result["message"]}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating pin status for {ticker}: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


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
        raise HTTPException(status_code=500, detail="Internal server error")


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
        raise HTTPException(status_code=500, detail="Internal server error")


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
        raise HTTPException(status_code=500, detail="Internal server error")