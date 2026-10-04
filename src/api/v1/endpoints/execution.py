"""
Execution & Real-Time Slippage Analytics Endpoints (P6 Engine).
=============================================================================
Provides RESTful API endpoints for recording trade execution fills, querying
asset-level calibrated slippage metrics, retrieving SOR algorithmic tuning
recommendations, and calculating empirical opportunity cost frictions.
"""
from __future__ import annotations

from typing import Dict, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status

from src.api.v1.dependencies import get_current_user_id
from src.api.v1.schemas.execution_slippage_schemas import (
    ExecutionFillRequest,
    ExecutionFillResponse,
    RoundtripFrictionResponse,
    SlippageMetricItemSchema,
    SlippageMetricsListResponse,
    SORAdaptationResponse,
)
from src.services.adaptive_execution_slippage_compensator import (
    AdaptiveExecutionSlippageCompensator,
    SlippageCompensationMetrics,
)
from src.services.settings_service import SettingsService
from src.utils.logger import setup_logger

logger = setup_logger("API_Execution")
router = APIRouter()

# In-memory service cache per user for state continuity
_compensators: Dict[str, AdaptiveExecutionSlippageCompensator] = {}


def get_slippage_compensator(
    user_id: str = Depends(get_current_user_id),
) -> AdaptiveExecutionSlippageCompensator:
    """Dependency provider for AdaptiveExecutionSlippageCompensator."""
    if user_id not in _compensators:
        settings_svc = SettingsService(user_id=user_id)
        settings_repo = getattr(settings_svc, "repo", None)
        _compensators[user_id] = AdaptiveExecutionSlippageCompensator(
            user_id=user_id,
            settings_repo=settings_repo,
        )
    return _compensators[user_id]


@router.post(
    "/slippage/feedback",
    response_model=ExecutionFillResponse,
    summary="回報成交並觸發自適應滑價校準",
)
def record_execution_feedback(
    payload: ExecutionFillRequest,
    compensator: AdaptiveExecutionSlippageCompensator = Depends(get_slippage_compensator),
) -> ExecutionFillResponse:
    """
    接收外部實盤或模擬訂單之成交回報，即時計算實際滑價、更新 EWMA 偏離補償乘數，
    並於偵測到逆向選擇時自動啟動安全防護緩衝。
    """
    try:
        fill = compensator.record_fill(
            order_id=payload.order_id,
            symbol=payload.symbol,
            action=payload.action,
            venue=payload.venue,
            fill_price=payload.fill_price,
            fill_quantity=payload.fill_quantity,
            arrival_price=payload.arrival_price,
            parent_plan_id=payload.parent_plan_id,
            market_price_at_fill=payload.market_price_at_fill,
            fee_usd=payload.fee_usd,
            adv_20=payload.adv_20,
        )
        metrics = compensator.get_metrics(payload.symbol)
        return ExecutionFillResponse(
            status="success",
            fill_id=fill.fill_id,
            symbol=fill.symbol,
            realized_slippage_bps=fill.realized_slippage_bps,
            is_anomaly=fill.is_anomaly,
            anomaly_reason=fill.anomaly_reason,
            calibrated_multiplier=metrics.slippage_multiplier,
            effective_slippage_bps=metrics.calibrated_effective_slippage_bps,
        )
    except Exception as e:
        logger.error(f"Failed to record execution fill feedback: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to record execution fill: {str(e)}",
        )


@router.get(
    "/slippage/metrics",
    response_model=SlippageMetricsListResponse,
    summary="獲取所有標的之即時滑價校準指標",
)
def list_slippage_metrics(
    compensator: AdaptiveExecutionSlippageCompensator = Depends(get_slippage_compensator),
) -> SlippageMetricsListResponse:
    """獲取當前記憶體中所有已校準標的之滑價偏離乘數、平均滑價與逆向選擇次數。"""
    all_metrics = compensator.get_all_metrics()
    formatted = {
        sym: SlippageMetricItemSchema(**m.to_dict())
        for sym, m in all_metrics.items()
    }
    return SlippageMetricsListResponse(status="success", metrics=formatted)


@router.get(
    "/slippage/metrics/{symbol}",
    response_model=SlippageMetricItemSchema,
    summary="獲取指定標的之即時滑價校準指標",
)
def get_symbol_slippage_metrics(
    symbol: str,
    compensator: AdaptiveExecutionSlippageCompensator = Depends(get_slippage_compensator),
) -> SlippageMetricItemSchema:
    """獲取單一指定標的之滑價指標；若尚無成交紀錄則回傳基準備援參數。"""
    metrics = compensator.get_metrics(symbol)
    return SlippageMetricItemSchema(**metrics.to_dict())


@router.get(
    "/slippage/recommendations/{symbol}",
    response_model=SORAdaptationResponse,
    summary="獲取指定標的之 SOR 自適應拆單調度建議",
)
def get_sor_adaptation_recommendations(
    symbol: str,
    base_slices: int = Query(5, ge=1, le=24, description="基準切片數"),
    base_window_minutes: int = Query(30, ge=5, le=240, description="基準執行視窗（分鐘）"),
    base_max_slippage_bps: float = Query(35.0, ge=5.0, le=150.0, description="基準熔斷滑價門檻"),
    order_quantity: Optional[float] = Query(None, description="預計委託股數"),
    adv_20: Optional[float] = Query(None, description="20日日均量"),
    compensator: AdaptiveExecutionSlippageCompensator = Depends(get_slippage_compensator),
) -> SORAdaptationResponse:
    """
    依據歷史成交滑價偏離乘數，動態推薦最適當之切片數、時間窗口長度、隨機微擾比例及自適應斷路器門檻。
    """
    params = compensator.get_sor_adaptation_parameters(
        symbol=symbol,
        base_slices=base_slices,
        base_window_minutes=base_window_minutes,
        base_max_slippage_bps=base_max_slippage_bps,
        order_quantity=order_quantity,
        adv_20=adv_20,
    )
    return SORAdaptationResponse(status="success", **params.to_dict())


@router.get(
    "/slippage/friction",
    response_model=RoundtripFrictionResponse,
    summary="計算兩標的間校準後雙向換手磨擦與機會成本門檻",
)
def get_calibrated_roundtrip_friction(
    sell_ticker: str = Query(..., description="賣出標的代碼"),
    buy_ticker: str = Query(..., description="買入標的代碼"),
    sell_fee_pct: float = Query(0.0005, ge=0.0, description="賣出手續費率"),
    buy_fee_pct: float = Query(0.0005, ge=0.0, description="買入手續費率"),
    friction_multiplier: float = Query(2.5, ge=1.0, description="摩擦倍數"),
    hurdle_rate: float = Query(0.010, ge=0.0, description="基礎超額要求門檻"),
    compensator: AdaptiveExecutionSlippageCompensator = Depends(get_slippage_compensator),
) -> RoundtripFrictionResponse:
    """
    計算標的 A 置換為標的 B 所需面對之真實兩向磨擦損耗與機會成本門檻。
    """
    assessment = compensator.get_calibrated_roundtrip_friction(
        sell_ticker=sell_ticker,
        buy_ticker=buy_ticker,
        sell_fee_pct=sell_fee_pct,
        buy_fee_pct=buy_fee_pct,
        friction_multiplier=friction_multiplier,
        hurdle_rate=hurdle_rate,
    )
    return RoundtripFrictionResponse(status="success", **assessment.to_dict())
