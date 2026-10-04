"""
Execution & Real-Time Slippage Analytics Endpoints (P6 Engine).
=============================================================================
Provides RESTful API endpoints for recording trade execution fills, querying
asset-level calibrated slippage metrics, retrieving SOR algorithmic tuning
recommendations, and calculating empirical opportunity cost frictions.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status

from src.api.v1.dependencies import get_current_user_id
from src.api.v1.schemas.circuit_breaker_schemas import (
    CircuitBreakerActionResponse,
    CircuitBreakerQuoteEvaluationRequest,
    CircuitBreakerQuoteEvaluationResponse,
    CircuitBreakerResumeRequest,
    CircuitBreakerStatusListResponse,
    CircuitBreakerStatusSchema,
    CircuitBreakerTriggerRequest,
    ContagionImpactSchema,
    SpilloverContagionResponse,
)
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
from src.services.intraday_liquidity_circuit_breaker_service import (
    IntradayLiquidityCircuitBreakerService,
    MarketQuoteObservation,
)
from src.services.cross_asset_volatility_spillover_service import (
    CrossAssetVolatilitySpilloverService,
    SpilloverContagionAssessment,
)
from src.services.order_book_toxicity_detector_service import (
    OrderBookDepthSnapshot,
    OrderBookToxicityDetectorService,
    ToxicityAssessment,
    TradeDirection,
    TradeTick,
)
from src.api.v1.schemas.toxicity_schemas import (
    RecordQuoteRequest,
    RecordTradeRequest,
    ToxicityAssessmentResponse,
)
from src.api.v1.schemas.hunt_guard_schemas import (
    GuardEvaluationRequest,
    GuardEvaluationResponse,
    GuardResetRequest,
    GuardStatusListResponse,
    KeyLevelSchema,
    LiquidityHoleAssessmentSchema,
    OrderBookSnapshotSchema,
    StopHuntAssessmentSchema,
    SymbolGuardStatusSchema,
    TradeBarSchema,
)
from src.services.intraday_liquidity_hunt_guard_service import (
    IntradayLiquidityHuntGuardService,
    KeyLevel,
    KeyLevelType,
    OrderBookSnapshot,
    TradeBar,
)
from src.services.settings_service import SettingsService
from src.utils.logger import setup_logger

logger = setup_logger("API_Execution")
router = APIRouter()

# In-memory service cache per user for state continuity
_compensators: Dict[str, AdaptiveExecutionSlippageCompensator] = {}
_circuit_breakers: Dict[str, IntradayLiquidityCircuitBreakerService] = {}
_spillover_services: Dict[str, CrossAssetVolatilitySpilloverService] = {}
_toxicity_services: Dict[str, OrderBookToxicityDetectorService] = {}
_hunt_guard_services: Dict[str, IntradayLiquidityHuntGuardService] = {}


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


def get_circuit_breaker_service(
    user_id: str = Depends(get_current_user_id),
) -> IntradayLiquidityCircuitBreakerService:
    """Dependency provider for IntradayLiquidityCircuitBreakerService."""
    if user_id not in _circuit_breakers:
        settings_svc = SettingsService(user_id=user_id)
        _circuit_breakers[user_id] = IntradayLiquidityCircuitBreakerService(
            user_id=user_id,
            settings_service=settings_svc,
        )
    return _circuit_breakers[user_id]


def get_spillover_service(
    user_id: str = Depends(get_current_user_id),
    cb_service: IntradayLiquidityCircuitBreakerService = Depends(get_circuit_breaker_service),
    compensator: AdaptiveExecutionSlippageCompensator = Depends(get_slippage_compensator),
) -> CrossAssetVolatilitySpilloverService:
    """Dependency provider for CrossAssetVolatilitySpilloverService (M7)."""
    if user_id not in _spillover_services:
        settings_svc = SettingsService(user_id=user_id)
        _spillover_services[user_id] = CrossAssetVolatilitySpilloverService(
            user_id=user_id,
            settings_service=settings_svc,
            circuit_breaker_service=cb_service,
            slippage_compensator=compensator,
        )
    return _spillover_services[user_id]


def get_toxicity_service(
    user_id: str = Depends(get_current_user_id),
    cb_service: IntradayLiquidityCircuitBreakerService = Depends(get_circuit_breaker_service),
    compensator: AdaptiveExecutionSlippageCompensator = Depends(get_slippage_compensator),
) -> OrderBookToxicityDetectorService:
    """Dependency provider for OrderBookToxicityDetectorService (E3)."""
    if user_id not in _toxicity_services:
        settings_svc = SettingsService(user_id=user_id)
        settings_repo = getattr(settings_svc, "repo", None)
        _toxicity_services[user_id] = OrderBookToxicityDetectorService(
            user_id=user_id,
            settings_repo=settings_repo,
            circuit_breaker_service=cb_service,
            slippage_compensator=compensator,
        )
    return _toxicity_services[user_id]


def get_hunt_guard_service(
    user_id: str = Depends(get_current_user_id),
) -> IntradayLiquidityHuntGuardService:
    """Dependency provider for IntradayLiquidityHuntGuardService (E4)."""
    if user_id not in _hunt_guard_services:
        settings_svc = SettingsService(user_id=user_id)
        _hunt_guard_services[user_id] = IntradayLiquidityHuntGuardService(
            user_id=user_id,
            settings_service=settings_svc,
        )
    return _hunt_guard_services[user_id]


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


# ── P7: Intraday Liquidity Circuit Breaker Endpoints ─────────────────────────


@router.get(
    "/circuit-breaker/status",
    response_model=CircuitBreakerStatusListResponse,
    summary="獲取當前所有標的之盤中流動性熔斷器狀態",
)
def list_circuit_breaker_statuses(
    service: IntradayLiquidityCircuitBreakerService = Depends(get_circuit_breaker_service),
) -> CircuitBreakerStatusListResponse:
    """查詢當前所有監控標的與全局之盤中流動性熔斷狀態（NORMAL, WARNING, TRIGGERED, COOLDOWN）。"""
    all_statuses = service.get_all_statuses()
    formatted = {
        sym: CircuitBreakerStatusSchema(**st.to_dict())
        for sym, st in all_statuses.items()
    }
    return CircuitBreakerStatusListResponse(
        status="success",
        total=len(formatted),
        circuit_breakers=formatted,
    )


@router.get(
    "/circuit-breaker/status/{symbol}",
    response_model=CircuitBreakerStatusSchema,
    summary="獲取指定標的之盤中流動性熔斷器狀態",
)
def get_symbol_circuit_breaker_status(
    symbol: str,
    service: IntradayLiquidityCircuitBreakerService = Depends(get_circuit_breaker_service),
) -> CircuitBreakerStatusSchema:
    """查詢單一標的或 GLOBAL 熔斷狀態、點差倍數、偏離幅度與冷卻倒數。"""
    st = service.get_status(symbol)
    return CircuitBreakerStatusSchema(**st.to_dict())


@router.post(
    "/circuit-breaker/assess",
    response_model=CircuitBreakerQuoteEvaluationResponse,
    summary="提交盤中報價並評估是否觸發流動性衝擊熔斷",
)
def assess_quote_for_circuit_breaker(
    payload: CircuitBreakerQuoteEvaluationRequest,
    service: IntradayLiquidityCircuitBreakerService = Depends(get_circuit_breaker_service),
) -> CircuitBreakerQuoteEvaluationResponse:
    """
    提交最新盤中買賣報價與實時波動率，評估點差突增、瞬時跳空或波動暴增是否突破閾值，
    若衝擊嚴重則自動觸發熔斷並進入冷卻期。
    """
    obs = MarketQuoteObservation(
        symbol=payload.symbol,
        bid_price=payload.bid_price,
        ask_price=payload.ask_price,
        last_price=payload.last_price,
        bid_size=payload.bid_size,
        ask_size=payload.ask_size,
        intraday_volatility=payload.intraday_volatility,
    )
    status_res = service.evaluate_quote(obs)
    return CircuitBreakerQuoteEvaluationResponse(
        status="success",
        circuit_breaker=CircuitBreakerStatusSchema(**status_res.to_dict()),
    )


@router.post(
    "/circuit-breaker/trigger",
    response_model=CircuitBreakerActionResponse,
    summary="手動緊急觸發盤中流動性熔斷",
)
def manually_trigger_circuit_breaker(
    payload: CircuitBreakerTriggerRequest,
    service: IntradayLiquidityCircuitBreakerService = Depends(get_circuit_breaker_service),
) -> CircuitBreakerActionResponse:
    """手動暫停特定標的或全局投資組合之交易執行，撤回掛單並鎖定冷卻期。"""
    res = service.manual_trigger(
        symbol=payload.symbol,
        reason=payload.reason,
        cooldown_minutes=payload.cooldown_minutes,
    )
    return CircuitBreakerActionResponse(
        status="success",
        symbol=res.symbol,
        state=res.state.value if hasattr(res.state, "value") else str(res.state),
        message=f"🚨 已成功對 {res.symbol} 觸發盤中流動性緊急熔斷，冷卻 {payload.cooldown_minutes} 分鐘。",
    )


@router.post(
    "/circuit-breaker/resume",
    response_model=CircuitBreakerActionResponse,
    summary="手動恢復盤中交易執行與解除熔斷",
)
def manually_resume_circuit_breaker(
    payload: CircuitBreakerResumeRequest,
    service: IntradayLiquidityCircuitBreakerService = Depends(get_circuit_breaker_service),
) -> CircuitBreakerActionResponse:
    """手動解除熔斷狀態，恢復正常 SOR 拆單與訂單路由執行。"""
    service.resume(payload.symbol)
    res = service.get_status(payload.symbol)
    return CircuitBreakerActionResponse(
        status="success",
        symbol=res.symbol,
        state=res.state.value if hasattr(res.state, "value") else str(res.state),
        message=f"🟢 已成功解除 {payload.symbol} 之盤中熔斷，恢復正常交易執行。",
    )


@router.get(
    "/circuit-breaker/spillover",
    response_model=SpilloverContagionResponse,
    summary="獲取當前跨資產波動率傳染矩陣與防禦防護狀態 (M7)",
)
def get_spillover_contagion_status(
    service: CrossAssetVolatilitySpilloverService = Depends(get_spillover_service),
) -> SpilloverContagionResponse:
    """
    查詢當前活躍的跨資產流動性衝擊傳染評估：
    包括活躍傳染源、受波及之關聯標的、調升後之滑價補償乘數及額外防禦現金儲備比率。
    """
    assessment: SpilloverContagionAssessment = service.evaluate_contagion()
    impacts_dict = {
        sym: ContagionImpactSchema(**impact.to_dict())
        for sym, impact in assessment.impacts.items()
    }
    return SpilloverContagionResponse(
        status="success",
        is_active=assessment.is_active,
        active_sources=assessment.active_sources,
        total_impacted_tickers=assessment.total_impacted_tickers,
        aggregate_cash_expansion_pct=assessment.aggregate_cash_expansion_pct,
        max_slippage_multiplier=assessment.max_slippage_multiplier,
        impacts=impacts_dict,
        evaluated_at=assessment.evaluated_at,
    )


@router.get(
    "/orderbook/toxicity",
    response_model=ToxicityAssessmentResponse,
    summary="查詢標的微觀訂單流毒性與深度失衡評估 (E3)",
)
def get_orderbook_toxicity(
    symbol: str = Query(..., description="標的代碼", examples=["NVDA"]),
    action: Optional[str] = Query(None, description="擬執行的交易方向 (BUY/SELL) 以評估逆向選擇風險", examples=["BUY"]),
    service: OrderBookToxicityDetectorService = Depends(get_toxicity_service),
) -> ToxicityAssessmentResponse:
    """
    查詢指定標的之 VPIN (Volume-Synchronized Probability of Toxicity) 與
    訂單簿深度失衡度 (OBI)，返回即時毒性等級與執行調節建議。
    """
    assessment: ToxicityAssessment = service.evaluate_toxicity(symbol, proposed_action=action)
    return ToxicityAssessmentResponse(**assessment.to_dict())


@router.post(
    "/orderbook/quote",
    response_model=ToxicityAssessmentResponse,
    summary="錄入最新盤口深度快照並更新微觀失衡 (E3)",
)
def record_orderbook_quote(
    payload: RecordQuoteRequest,
    service: OrderBookToxicityDetectorService = Depends(get_toxicity_service),
) -> ToxicityAssessmentResponse:
    """
    接收最新 Level-1 / Level-2 最佳買賣報價與掛單深度，
    即時更新 Order Book Imbalance (OBI) 並返回最新毒性評估。
    """
    snapshot = OrderBookDepthSnapshot(
        symbol=payload.symbol,
        bid_price=payload.bid_price,
        ask_price=payload.ask_price,
        bid_size=payload.bid_size,
        ask_size=payload.ask_size,
    )
    service.record_quote(snapshot)
    assessment = service.evaluate_toxicity(payload.symbol)
    return ToxicityAssessmentResponse(**assessment.to_dict())


@router.post(
    "/orderbook/trade",
    response_model=ToxicityAssessmentResponse,
    summary="錄入逐筆成交 Tick 並推進 VPIN 交易量時鐘 (E3)",
)
def record_orderbook_trade(
    payload: RecordTradeRequest,
    service: OrderBookToxicityDetectorService = Depends(get_toxicity_service),
) -> ToxicityAssessmentResponse:
    """
    接收最新市場逐筆成交回報，將成交量分配至固定體積的 VPIN 交易量桶，
    計算主動買賣方失衡比例並返回最新毒性評估。
    """
    direction = None
    if payload.direction:
        try:
            direction = TradeDirection(payload.direction.upper())
        except ValueError:
            direction = TradeDirection.UNKNOWN

    tick = TradeTick(
        symbol=payload.symbol,
        price=payload.price,
        volume=payload.volume,
        direction=direction,
    )
    service.record_trade(tick)
    assessment = service.evaluate_toxicity(payload.symbol)
    return ToxicityAssessmentResponse(**assessment.to_dict())


# ============================================================================
# E4 Engine: Intraday Liquidity Hole & Stop-Hunt Guard Endpoints
# ============================================================================


@router.post(
    "/guard/evaluate",
    response_model=GuardEvaluationResponse,
    summary="評估日內流動性空洞與假突破獵殺防線 (E4)",
)
def evaluate_microstructure_guard(
    payload: GuardEvaluationRequest,
    guard_service: IntradayLiquidityHuntGuardService = Depends(get_hunt_guard_service),
) -> GuardEvaluationResponse:
    """
    接收最新盤口報價快照 (OrderBookSnapshot)、K線 (TradeBar) 與關鍵價位，
    計算盤口深度枯竭比率 (DDR)、假突破掃蕩評分 (SHS) 與防禦狀態機。
    返回執行建議動作 (PROCEED_NORMAL, DELAY_EXECUTION, FORCE_PASSIVE_LIMIT, ABORT_BREAKOUT_CHASE)
    以及額外逆向選擇滑價保護緩衝 (adverse_slippage_buffer_bps)。
    """
    snapshot = None
    if payload.snapshot:
        snapshot = OrderBookSnapshot(
            symbol=payload.snapshot.symbol,
            bid_price=payload.snapshot.bid_price,
            ask_price=payload.snapshot.ask_price,
            bid_size=payload.snapshot.bid_size,
            ask_size=payload.snapshot.ask_size,
            timestamp=payload.snapshot.timestamp or datetime.now(timezone.utc),
        )

    bar = None
    if payload.bar:
        bar = TradeBar(
            symbol=payload.bar.symbol,
            open_price=payload.bar.open_price,
            high_price=payload.bar.high_price,
            low_price=payload.bar.low_price,
            close_price=payload.bar.close_price,
            volume=payload.bar.volume,
            timestamp=payload.bar.timestamp or datetime.now(timezone.utc),
        )

    key_levels = None
    if payload.key_levels:
        key_levels = [
            KeyLevel(
                level_type=kl.level_type,
                price=kl.price,
                description=kl.description,
            )
            for kl in payload.key_levels
        ]

    eval_result = guard_service.evaluate_guard(
        symbol=payload.symbol,
        snapshot=snapshot,
        bar=bar,
        key_levels=key_levels,
    )

    return GuardEvaluationResponse(
        symbol=eval_result.symbol,
        state=eval_result.state,
        action=eval_result.action,
        liquidity_hole=LiquidityHoleAssessmentSchema(
            is_hole_detected=eval_result.liquidity_hole.is_hole_detected,
            depth_depletion_ratio=eval_result.liquidity_hole.depth_depletion_ratio,
            current_depth=eval_result.liquidity_hole.current_depth,
            baseline_depth=eval_result.liquidity_hole.baseline_depth,
            spread_bps=eval_result.liquidity_hole.spread_bps,
            spread_expansion_ratio=eval_result.liquidity_hole.spread_expansion_ratio,
            details=eval_result.liquidity_hole.details,
        ),
        stop_hunt=StopHuntAssessmentSchema(
            is_hunt_detected=eval_result.stop_hunt.is_hunt_detected,
            stop_hunt_score=eval_result.stop_hunt.stop_hunt_score,
            swept_level=eval_result.stop_hunt.swept_level,
            level_type=eval_result.stop_hunt.level_type,
            penetration_pct=eval_result.stop_hunt.penetration_pct,
            reversion_ratio=eval_result.stop_hunt.reversion_ratio,
            volume_spike_ratio=eval_result.stop_hunt.volume_spike_ratio,
            details=eval_result.stop_hunt.details,
        ),
        recommended_delay_seconds=eval_result.recommended_delay_seconds,
        adverse_slippage_buffer_bps=eval_result.adverse_slippage_buffer_bps,
        evaluated_at=eval_result.evaluated_at,
    )


@router.get(
    "/guard/status",
    response_model=GuardStatusListResponse,
    summary="查詢所有監控標的之獵殺防線狀態與冷卻資訊 (E4)",
)
def get_all_guard_statuses(
    guard_service: IntradayLiquidityHuntGuardService = Depends(get_hunt_guard_service),
) -> GuardStatusListResponse:
    """
    返回目前記憶體內所有追蹤資產的防線狀態機、是否處於冷卻期、剩餘冷卻秒數及最近觸發詳情。
    """
    all_states = guard_service.get_all_guard_states()
    items = {
        sym: SymbolGuardStatusSchema(**data)
        for sym, data in all_states.items()
    }
    return GuardStatusListResponse(
        total_symbols=len(items),
        symbols=items,
    )


@router.post(
    "/guard/reset",
    summary="手動重設指定標的之防線狀態至 NORMAL (E4)",
)
def reset_guard_status(
    payload: GuardResetRequest,
    guard_service: IntradayLiquidityHuntGuardService = Depends(get_hunt_guard_service),
) -> Dict[str, Any]:
    """
    手動重設標的之微結構防護狀態，解除冷卻期並恢復為 NORMAL。
    """
    guard_service.reset_symbol_state(payload.symbol)
    return {
        "status": "success",
        "symbol": payload.symbol.upper().strip(),
        "current_state": "NORMAL",
        "message": f"Guard state for {payload.symbol.upper()} has been reset to NORMAL.",
    }



