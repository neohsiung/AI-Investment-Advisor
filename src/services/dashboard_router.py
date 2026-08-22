from fastapi import APIRouter, HTTPException, Depends, Request, Body, UploadFile, File, BackgroundTasks
from fastapi.responses import StreamingResponse
from sqlalchemy import text
from typing import Dict, Any, List
import pandas as pd
import io
import re
import httpx
import os
import json
import asyncio
from src.services.dashboard_service import DashboardService
from src.utils.logger import setup_logger
from src.utils.jwt_utils import decode_token
from src.services.performance_service import PerformanceService
from src.repositories.report_repository import AsyncAlchemyReportRepository
from src.utils.rate_limit import limiter
from src.services.transaction_service import TransactionService
from src.services.settings_service import SettingsService
from src.services.intelligence_service import IntelligenceService
from src.utils.security import redact_pii
# PAD Phase 2: Replace AgentFactory with model router and gateway
from src.infrastructure.llm.tier_config import SettingsAwareModelRouter
from src.infrastructure.llm.llm_gateway import OpenRouterGateway
from src.domain.interfaces import Message, LLMConfig
from src.repositories.settings_repository import AlchemySettingsRepository

logger = setup_logger("DashboardRouter")
dashboard_router = APIRouter(tags=["Dashboard"])

# PAD Phase 2: Module-level initialization of model router and gateway
# These are shared across all route handlers within this router
_model_router = None
_gateway = None
_settings_repo_cache = {}

def get_model_router_and_gateway(user_id: str):
    """Lazy initialization of model router and gateway per user context"""
    global _model_router, _gateway, _settings_repo_cache
    
    if _model_router is None:
        _model_router = SettingsAwareModelRouter(None)
    
    if _gateway is None:
        _gateway = OpenRouterGateway()
    
    # Initialize settings repo for this user if not cached
    if user_id not in _settings_repo_cache:
        from src.data.database import get_db_engine
        _settings_repo_cache[user_id] = AlchemySettingsRepository(engine=get_db_engine())
    
    return _model_router, _gateway, _settings_repo_cache[user_id]

async def _call_agent_llm(user_id: str, context: Dict[str, Any], tier: str = "smart", 
                           temperature: float = 0.7, max_tokens: int = 2000) -> str:
    """
    PAD Phase 2: Replace AgentFactory.create_cio_agent().call_llm() with direct gateway calls.
    Generic method to call LLM for CIO agent role.
    """
    try:
        model_router, gateway, settings_repo = get_model_router_and_gateway(user_id)
        
        # Update router with current settings repo
        model_router.settings_repo = settings_repo
        
        model = model_router.get_model(user_id, tier)
        if not model:
            logger.warning(f"Failed to route model for tier={tier}, falling back to default")
            model = "claude-3.5-sonnet"  # Fallback model
        
        system_prompt = (
            "You are a professional AI Investment Advisor. "
            "Your goal is to answer the user's financial questions concisely, directly, and interactively. "
            "Provide actionable, insightful, and data-driven responses. "
            "Use traditional Chinese (繁體中文)."
        )
        
        messages = [
            Message(role="system", content=system_prompt),
            Message(role="user", content=json.dumps(context))
        ]
        
        config = LLMConfig(
            provider=os.getenv("AI_PROVIDER", "OpenRouter"),
            model=model,
            temperature=temperature,
            max_tokens=max_tokens
        )
        
        logger.debug(f"DashboardRouter: Calling CIO agent via {model}")
        response = await gateway.chat(messages, config)
        
        if not isinstance(response, str):
            raise ValueError(f"Unexpected response type from gateway: {type(response)}")
        
        return response
    except Exception as e:
        logger.error(f"DashboardRouter: CIO agent LLM call failed: {e}")
        raise

def get_current_user(request: Request) -> Dict[str, Any]:
    """從 Header 或 Cookie 驗證 JWT 並獲取使用者資訊"""
    token = None
    
    # 1. 優先檢查 Authorization Header (Sprint 3 localStorage 機制)
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header.split(" ")[1]
        
    # 2. 回退檢查 Cookie (舊版機制)
    if not token:
        token = request.cookies.get("access_token")
        
    if not token:
        logger.warning("Missing access_token in Authorization header and cookies")
        raise HTTPException(status_code=401, detail="Not authenticated")
        
    payload = decode_token(token)
    if not payload or payload.get("type") != "access":
        logger.warning("Invalid or expired access_token")
        raise HTTPException(status_code=401, detail="Invalid token")
        
    return payload

def get_dashboard_service(user: Dict[str, Any] = Depends(get_current_user)) -> DashboardService:
    """獲取 DashboardService 實例，嚴格綁定當前使用者 (User Isolation)"""
    user_id = user.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="User ID not found in token")
    
    # 動態實例化並返回綁定該 User ID 的 Service
    return DashboardService(user_id=user_id)

def get_performance_service(user: Dict[str, Any] = Depends(get_current_user)) -> PerformanceService:
    """獲取 PerformanceService 實例"""
    user_id = user.get("sub")
    return PerformanceService(user_id=user_id)

def get_reports_repository(user: Dict[str, Any] = Depends(get_current_user)) -> AsyncAlchemyReportRepository:
    """獲取 AsyncAlchemyReportRepository 實例"""
    return AsyncAlchemyReportRepository()

@dashboard_router.get("/health")
async def health_check():
    """系統健康檢查 (DB, Redis, Celery)"""
    health = {"status": "healthy", "components": {}}
    
    # 1. Check DB
    try:
        from src.data.database import get_db_engine
        engine = get_db_engine()
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        health["components"]["database"] = "ok"
    except Exception as e:
        health["status"] = "degraded"
        health["components"]["database"] = f"error: {str(e)}"

    # 2. Check Redis/Celery
    try:
        # 2026-08-02: was `from src.infrastructure.tasks import celery_app`, but
        # that module exposes the Celery instance as `app` (tasks.py:5) — there
        # has never been a `celery_app` attribute. The ImportError fell into the
        # except below, so this endpoint reported "degraded" and answered 503
        # unconditionally, regardless of how healthy the workers actually were.
        # 2026-08-02：原本 import 的名稱在該模組不存在（tasks.py:5 匯出的是 app），
        # ImportError 被下面的 except 接住，導致此端點無條件回報 degraded / 503。
        from src.infrastructure.celery_app import app as celery_app
        # Ping returns 'pong' if connection is alive
        ping = celery_app.control.ping(timeout=1.0)
        if ping:
            health["components"]["celery_workers"] = f"active ({len(ping)})"
        else:
            health["components"]["celery_workers"] = "no active workers"
            health["status"] = "degraded"
    except Exception as e:
        health["components"]["celery_workers"] = f"error: {str(e)}"
        health["status"] = "degraded"

    if health["status"] == "healthy":
        return health
    else:
        raise HTTPException(status_code=503, detail=health)

@dashboard_router.get("/reports")
async def get_reports(repo: AsyncAlchemyReportRepository = Depends(get_reports_repository), user: Dict[str, Any] = Depends(get_current_user)):
    """獲獲取最新的投資分析報告 (Async)"""
    try:
        user_id = user.get("sub", "demo_user")
        reports = await repo.get_latest_reports(user_id=user_id)
        return {
            "status": "success",
            "data": reports
        }
    except Exception as e:
        logger.exception("Error fetching reports")
        raise HTTPException(status_code=500, detail="Failed to fetch reports")

@dashboard_router.post("/rebalance")
@limiter.limit("1/5minute")
async def trigger_rebalance(
    request: Request,
    background_tasks: BackgroundTasks,
    user: Dict[str, Any] = Depends(get_current_user)
):
    """手動觸發投資組合再平衡 (非同步背景執行)"""
    try:
        user_id = user.get("sub")
        from src.infrastructure.tasks import trigger_portfolio_rebalance
        
        # v6.3: Dispatch to Celery if available, or fallback to BackgroundTasks
        # For simplicity in local dev, we call the task function via Celery .delay()
        # if Celery is not running, researchers can use background_tasks.add_task
        trigger_portfolio_rebalance.delay(user_id=user_id)
        
        return {
            "status": "success",
            "message": "再平衡指令已發送至哨兵監控系統，正在進行資產評估。"
        }
    except Exception as e:
        logger.error(f"Error triggering rebalance: {e}")
        # v9.1: Sanitization - do not leak raw exception details (e.g. IP addresses)
        raise HTTPException(status_code=500, detail="Failed to trigger rebalance flow")


def get_transaction_service(user: Dict[str, Any] = Depends(get_current_user)) -> TransactionService:
    """獲取 TransactionService 實例"""
    user_id = user.get("sub")
    return TransactionService(user_id=user_id)

def get_settings_service(user: Dict[str, Any] = Depends(get_current_user)) -> SettingsService:
    """獲取 SettingsService 實例"""
    user_id = user.get("sub")
    return SettingsService(user_id=user_id)

@dashboard_router.get("/settings")
async def get_all_settings(service: SettingsService = Depends(get_settings_service)):
    """獲取使用者的所有系統設定"""
    try:
        settings = service.get_all_settings()
        return {
            "status": "success",
            "data": settings
        }
    except Exception as e:
        logger.exception("Error fetching settings")
        raise HTTPException(status_code=500, detail="Internal server error while fetching settings")

@dashboard_router.post("/settings")
@limiter.limit("10/minute")
async def save_settings(
    request: Request,
    payload: Dict[str, Any] = Body(...),
    service: SettingsService = Depends(get_settings_service),
):
    """
    批次儲存系統設定 (同步寫入)。

    2026-08-02: made synchronous alongside /api/v1/settings. This legacy route
    writes the same keys — leaving it fire-and-forget would keep a back door
    where a broker-credential or kill-switch write silently fails with a 200.
    2026-08-02：與 /api/v1/settings 一併改同步；這條舊路由寫的是同一批 key，
    留著背景寫入等於留一個「寫失敗卻回 200」的後門。
    """
    try:
        ok, message = service.save_settings_bulk(payload)
        if not ok:
            # See the identical treatment in src/api/v1/endpoints/settings.py:
            # the service message goes to the log only, never into the response.
            # 同 src/api/v1/endpoints/settings.py：服務訊息只進 log，不進回應。
            logger.error(f"Error saving settings: {message}")
            raise HTTPException(status_code=500, detail="Failed to save settings")
        return {"status": "success", "message": "設定已儲存。"}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error saving settings")
        raise HTTPException(status_code=500, detail="System update failed")

@dashboard_router.post("/settings/test-notification")
async def test_notification(
    payload: Dict[str, Any] = Body(...),
    user: Dict[str, Any] = Depends(get_current_user)
):
    """直接通過 TelegramAdapter 發送測試通知"""
    try:
        user_id = user.get("sub")
        channels = payload.get("channels", ["telegram"])
        
        # 延遲導入以避免循環依賴
        from src.infrastructure.channels.telegram_adapter import TelegramAdapter
        adapter = TelegramAdapter()
        
        results = {}
        for channel in channels:
            if channel == "telegram":
                try:
                    ok = await adapter.send_alert(
                        user_id=user_id,
                        title="🧪 Quantum AI 系統測試",
                        content="如果您看到這則訊息，代表您的通知管道配置成功！",
                        raise_error=True,
                    )
                    results[channel] = ok
                except Exception as e:
                    logger.error(f"Telegram test failed: {e}")
                    results[channel] = False
                    raise HTTPException(status_code=500, detail="發送失敗，通知發送服務異常。")
            else:
                results[channel] = False
        
        return {
            "status": "success",
            "message": "測試通知已發送",
            "debug": results
        }
            
    except Exception as e:
        logger.exception("Error triggering test notification")
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(status_code=500, detail="Notification test failed")

@dashboard_router.get("/settings/models")
async def get_available_models(service: SettingsService = Depends(get_settings_service)):
    """獲取可用的 AI 模型列表 (從 OpenRouter)"""
    try:
        models = service.fetch_openrouter_models()
        return {
            "status": "success",
            "data": models
        }
    except Exception as e:
        logger.exception("Error fetching models")
        raise HTTPException(status_code=500, detail="Failed to retrieve AI model list")

@dashboard_router.get("/data/transactions")
async def get_transactions(service: TransactionService = Depends(get_transaction_service)):
    """獲取使用者的所有交易紀錄"""
    try:
        df = service.get_transactions()
        return {
            "status": "success",
            "data": df.to_dict(orient='records')
        }
    except Exception as e:
        logger.exception("Error fetching transactions")
        raise HTTPException(status_code=500, detail="Internal error retrieving transactions")

@dashboard_router.post("/data/transactions")
async def add_transaction(
    payload: Dict[str, Any] = Body(...),
    service: TransactionService = Depends(get_transaction_service)
):
    """手動新增交易紀錄"""
    try:
        ticker = payload.get("ticker", "").upper()
        date_str = payload.get("date")
        action = payload.get("action")
        quantity = float(payload.get("quantity", 0))
        price = float(payload.get("price", 0))
        fees = float(payload.get("fees", 0))

        success, msg = service.add_manual_trade(ticker, date_str, action, quantity, price, fees)
        if not success:
            logger.error(f"Transaction add failed for {redact_pii(service.user_id)}: {msg}")
            raise HTTPException(status_code=400, detail="交易新增失敗，請檢查輸入數據格式")
            
        return {"status": "success", "message": "交易已成功新增"}
    except Exception as e:
        logger.exception("Error adding transaction")
        if isinstance(e, HTTPException): raise e
        raise HTTPException(status_code=500, detail="Transaction creation failed due to internal error")

@dashboard_router.delete("/data/transactions/{transaction_id}")
async def delete_transaction(
    transaction_id: str,
    service: TransactionService = Depends(get_transaction_service)
):
    """刪除特定的交易紀錄"""
    try:
        success, msg = service.delete_transaction(transaction_id)
        if not success:
            logger.error(f"Transaction deletion failed for {redact_pii(service.user_id)} (ID: {transaction_id}): {msg}")
            raise HTTPException(status_code=400, detail="交易刪除失敗，該交易可能不存在或權限不足")
            
        return {"status": "success", "message": "交易已成功刪除"}
    except Exception as e:
        logger.exception("Error deleting transaction")
        if isinstance(e, HTTPException): raise e
        raise HTTPException(status_code=500, detail="Transaction deletion failed due to internal error")


@dashboard_router.post("/data/capital-flow")
async def set_capital_flow(
    payload: Dict[str, Any] = Body(...),
    user: Dict[str, Any] = Depends(get_current_user),
):
    """
    設定真實投入資本基準（用於 ROI 計算）。
    由於 eToro API 不提供累積入金總額，需手動從 eToro UI 確認後設定。

    Body:
      - amount: float  (必填) — 從 eToro 帳戶 → 「我的投資組合」→「存款」取得的累積真實入金總額
      - date:   str    (選填) — YYYY-MM-DD，預設為今日
      - replace: bool  (選填) — 是否先刪除現有 MANUAL_CAPITAL 記錄，預設 True

    Set the real invested capital baseline for ROI calculation.
    Since eToro's API doesn't expose cumulative real deposits, set this manually
    from eToro UI → My Portfolio → Deposits total.
    """
    try:
        from src.data.database import get_db_engine
        from src.repositories.transaction_repository import (
            AlchemyTransactionRepository,
            ENTRY_CATEGORY_CAPITAL_FLOW,
        )
        from datetime import date as date_cls
        from sqlalchemy import text as sqla_text

        user_id = user.get("sub")
        amount = float(payload.get("amount", 0))
        deposit_date = payload.get("date") or date_cls.today().isoformat()
        replace = payload.get("replace", True)

        if amount <= 0:
            raise HTTPException(status_code=400, detail="amount must be > 0")

        engine = get_db_engine()

        # Optionally remove previous MANUAL_CAPITAL entries
        deleted = 0
        if replace:
            with engine.begin() as conn:
                result = conn.execute(
                    sqla_text("""
                        DELETE FROM transactions
                        WHERE user_id = :uid
                          AND entry_category = 'capital_flow'
                          AND source_file = 'MANUAL_CAPITAL'
                    """),
                    {"uid": user_id},
                )
                deleted = result.rowcount

        tx_repo = AlchemyTransactionRepository(engine)
        tx_repo.add(
            user_id=user_id,
            ticker="USD",
            date=deposit_date,
            action="DEPOSIT",
            quantity=1.0,
            price=amount,
            fees=0.0,
            leverage=1.0,
            source_file="MANUAL_CAPITAL",
            entry_category=ENTRY_CATEGORY_CAPITAL_FLOW,
            amount=amount,
        )
        logger.info(f"capital_flow set: user={user_id} amount={amount} date={deposit_date} replaced={deleted}")

        return {
            "status": "success",
            "data": {
                "net_invested_capital": round(amount, 2),
                "date": deposit_date,
                "replaced_records": deleted,
            },
            "message": f"已設定投入資本 ${amount:,.2f}。ROI 計算將使用此基準值。",
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error setting capital flow: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to set capital flow")




@dashboard_router.post("/chat")
@limiter.limit("5/minute")
async def advisor_chat(
    request: Request,
    payload: Dict[str, Any] = Body(...),
    user: Dict[str, Any] = Depends(get_current_user)
):
    """AI 投資顧問對話介面 (即時諮詢模式)"""
    try:
        user_id = user.get("sub", "demo_user")
        prompt = payload.get("message", "")
        history = payload.get("history", [])

        if not prompt:
            raise HTTPException(status_code=400, detail="Message is required")

        # 檢測 Ticker 標的
        ticker_match = re.search(r'\b([A-Z]{1,5})\b', prompt)
        ticker = ticker_match.group(1) if ticker_match else None

        system_prompt = (
            "You are a professional AI Investment Advisor. "
            "Your goal is to answer the user's financial questions concisely, directly, and interactively. "
            "Provide actionable, insightful, and data-driven responses. "
            "Use traditional Chinese (繁體中文)."
        )
        
        if ticker:
            system_prompt += f"\n\nThe user is asking about the ticker: {ticker}. Please focus your advice on this asset if relevant."

        messages = [{"role": "system", "content": system_prompt}]
        
        # 加上歷史紀錄 (上限 10 則)
        for msg in history[-10:]:
            messages.append(msg)
            
        messages.append({"role": "user", "content": prompt})

        # PAD Phase 2: Replace AgentFactory with _call_agent_llm
        context = {
            "user_id": user_id,
            "messages": messages,
            "ticker": ticker
        }
        response = await _call_agent_llm(user_id, context, tier="smart", temperature=0.7, max_tokens=2000)

        return {
            "status": "success",
            "data": {
                "message": response,
                "detected_ticker": ticker
            }
        }
    except Exception as e:
        logger.exception("Chat error")
        raise HTTPException(status_code=500, detail="Advisor chat assistance temporarily unavailable")
@dashboard_router.post("/chat/stream")
@limiter.limit("5/minute")
async def advisor_chat_stream(
    request: Request,
    payload: Dict[str, Any] = Body(...),
    user: Dict[str, Any] = Depends(get_current_user)
):
    """AI 投資顧問對話介面 (串流模式)"""
    try:
        user_id = user.get("sub", "demo_user")
        prompt = payload.get("message", "")
        history = payload.get("history", [])

        if not prompt:
            raise HTTPException(status_code=400, detail="Message is required")

        # 檢測 Ticker 標的
        ticker_match = re.search(r'\b([A-Z]{1,5})\b', prompt)
        ticker = ticker_match.group(1) if ticker_match else None

        system_prompt = (
            "You are a professional AI Investment Advisor. "
            "Your goal is to answer the user's financial questions concisely and directly. "
            "Provide actionable and data-driven responses. "
            "Use traditional Chinese (繁體中文)."
        )
        if ticker:
            system_prompt += f"\n\nThe user is asking about the ticker: {ticker}."

        messages = [{"role": "system", "content": system_prompt}]
        for msg in history[-10:]:
            messages.append(msg)
        messages.append({"role": "user", "content": prompt})

        # 定義串流產生器
        async def event_generator():
            try:
                from src.repositories.pulse_repository import AsyncPulseRepository
                from src.utils.async_utils import to_thread
                pulse_repo = AsyncPulseRepository()
                
                # Context dict for LLM call
                context = {
                    "user_id": user_id,
                    "task_instruction": prompt,
                    "topic": ticker or "General",
                    "messages": messages
                }
                
                # PAD Phase 2: Replace AgentFactory with _call_agent_llm
                logger.debug(f"Starting streaming response for user {user_id}")
                
                # Call LLM and get response
                response = await _call_agent_llm(user_id, context, tier="smart", temperature=0.7, max_tokens=2000)
                
                # Yield the response in chunks to simulate typewriter effect
                # Split roughly by words to simulate LLM stream
                chunks = re.findall(r'\S+|\n|\s+', response)
                for c in chunks:
                    yield f"data: {json.dumps({'chunk': c})}\n\n"
                    await asyncio.sleep(0.01)
                    
                yield "data: [DONE]\n\n"
            except Exception as e:
                logger.error(f"Streaming error in generator: {e}")
                yield f"data: {json.dumps({'error': 'Live assistance stream interrupted'})}\n\n"

        return StreamingResponse(event_generator(), media_type="text/event-stream")

    except Exception as e:
        logger.exception("Stream Chat error")
        raise HTTPException(status_code=500, detail="Live assistance stream interrupted")

@dashboard_router.get("/summary")
async def get_summary(service: DashboardService = Depends(get_dashboard_service)):
    """獲取投資概覽數據 (NLV, Cash, PnL, ROI) — Redis cached (120s TTL)"""
    from src.infrastructure.cache.redis_client import get_redis_sync
    cache_key = f"dashboard:summary:{service.user_id}"
    _r = None

    # Fast path: return cached result if available
    # 2026-08-10: was a fresh redis.from_url() per request; now the shared pool.
    # NOTE: the setex() below is unreachable — it sits after the `return` in the
    # success branch — so this cache is only ever read, never written, and every
    # request falls through to a full recompute. Left as-is here because fixing
    # it turns a 120s cache on, which is a behaviour change, not a leak fix.
    # 2026-08-10：改用共用連線池。注意：下方 setex() 位於 return 之後而永不執行，
    # 此快取只讀不寫；修正它等同啟用 120 秒快取，屬行為變更，故此處不動。
    try:
        _r = get_redis_sync()
        cached = _r.get(cache_key)
        if cached:
            return json.loads(cached)
    except Exception as e:# nosec B110
        logger.warning(f'Exception in dashboard_router.py: {e}', exc_info=True)

    try:
        data = service.prepare_dashboard_data(service.user_id)
        metrics = data.get('metrics', {})
        pnl = data.get('pnl_data', {})
        warnings = data.get('warnings', [])
        
        return {
            "status": "success" if not warnings else "partial",
            "data": {
                "total_valuation": metrics.get('nlv', 0),
                "uninvested_cash": metrics.get('cash_balance', 0),
                "gross_exposure": metrics.get('gross_nlv', 0),
                "leverage_ratio": metrics.get('leverage_ratio', 0),
                "active_agents": metrics.get('active_agents', 7),
                "risk_exposure": metrics.get('risk_level', "MODERATE"),
                "total_pnl": pnl.get('total', 0),
                "unrealized_pnl": pnl.get('unrealized', 0),
                "roi_percentage": data.get('roi', 0) * 100,
                "performance_change": "+1.2%" # 暫時模擬，未來可從歷史數據計算
            },
            "system_warnings": warnings
        }

        # Cache the result for 120 seconds
        try:
            if _r:
                _r.set(cache_key, json.dumps(result), ex=120)
        except Exception as e:# nosec B110
            logger.warning(f'Exception in dashboard_router.py: {e}', exc_info=True)

        return result
    except Exception as e:
        logger.exception(f"Error fetching dashboard summary: {e}")
        raise HTTPException(status_code=500, detail="Internal server error during dashboard summary calculation")

@dashboard_router.get("/positions")
async def get_positions(service: DashboardService = Depends(get_dashboard_service)):
    """獲取持倉清單"""
    try:
        data = service.prepare_dashboard_data(service.user_id)
        positions_df = data.get('positions_df', pd.DataFrame())
        warnings = data.get('warnings', [])
        
        return {
            "status": "success" if not warnings else "partial",
            "data": positions_df.to_dict(orient='records') if not positions_df.empty else [],
            "system_warnings": warnings
        }
    except Exception as e:
        logger.exception(f"Error fetching positions: {e}")
        raise HTTPException(status_code=500, detail="Internal server error during positions aggregation")

    # 這裡未來應從 SentinelService 獲取真實狀態
    # 目前返回符合 7 Agent Swarm 架構的預設列表
    return {
        "status": "success",
        "data": [
            {"id": "CIO-ALPHA", "name": "Chief Investment Officer", "strategy": "FRACTAL DEBATE", "performance": "+2.4%", "status": "Optimizing", "color": "bg-primary"},
            {"id": "SENT-01", "name": "Sentinel Radar", "strategy": "RISK GUARD", "performance": "N/A", "status": "Scanning", "color": "bg-secondary"},
            {"id": "FUND-02", "name": "Fundamental Analyst", "strategy": "VALUATION", "performance": "+1.1%", "status": "Idle", "color": "bg-tertiary"},
            {"id": "MOMT-03", "name": "Momentum Engine", "strategy": "TREND FOLLOWING", "performance": "+4.2%", "status": "Optimizing", "color": "bg-secondary"},
            {"id": "SENTI-04", "name": "Sentiment Scanner", "strategy": "SOCIAL NLP", "performance": "-0.5%", "status": "Scanning", "color": "bg-tertiary"},
            {"id": "ENG-PRO", "name": "Engineer Agent", "strategy": "AUTO OPTIMIZE", "performance": "N/A", "status": "Idle", "color": "bg-primary"},
            {"id": "SKILL-RT", "name": "Skill Router", "strategy": "TASK ALLOCATION", "performance": "N/A", "status": "Optimizing", "color": "bg-secondary"}
        ]
    }

@dashboard_router.get("/intelligence")
async def get_intelligence(user: Dict[str, Any] = Depends(get_current_user)):
    """獲取最新的市場情報簡報 (優先從快取讀取)"""
    try:
         user_id = user.get("sub") or "default_user"
         service = IntelligenceService(user_id=user_id)
         # v2.2: 優先讀取背景快取資料
         briefing = await service.get_latest_briefing()
         return {"status": "success", "data": briefing}
    except Exception as e:
         logger.error(f"Error fetching intelligence: {e}")
         # 回傳降級資料以防前端崩潰
         return {
             "status": "success",
             "data": {
                 "executive_summary": "市場情報獲取失敗，背景任務可能正在執行中。",
                 "recommendation": "請稍後再試",
                 "ai_note": "ERROR_REPORTED",
                 "observation_window": "OFFLINE",
                 "sentiment_metrics": []
             }
         }


@dashboard_router.get("/performance/history")
async def get_performance_history(service: PerformanceService = Depends(get_performance_service)):
    """獲取投資組合歷史績效 (用於圖表)"""
    try:
        history_df = service.reconstruct_history(service.user_id)
        if history_df.empty:
            return {"status": "success", "data": []}
        return {
            "status": "success",
            "data": history_df.to_dict(orient='records')
        }
    except Exception as e:
        logger.exception("Error fetching performance history")
        raise HTTPException(status_code=500, detail="Failed to reconstruct portfolio history")

@dashboard_router.get("/performance/agents")
async def get_agent_performance_stats(service: PerformanceService = Depends(get_performance_service)):
    """獲取各代理人績效統計"""
    try:
        stats = service.get_agent_performance()
        return {
            "status": "success",
            "data": stats
        }
    except Exception as e:
        logger.exception("Error fetching agent performance")
        raise HTTPException(status_code=500, detail="Agent statistics unavailable")

@dashboard_router.get("/agents")
async def get_agent_status_list(user: Dict[str, Any] = Depends(get_current_user)):
    """獲取 Agent 運行狀態列表（從 agent_performance 表）"""
    try:
        from src.repositories.agent_repository import AlchemyAgentRepository
        repo = AlchemyAgentRepository()
        # Direct execution since we need specific columns
        rows = repo.db.execute(
            text("SELECT agent_name, tier, success_count, failure_count, avg_latency, last_updated "
                 "FROM agent_performance ORDER BY agent_name")
        ).fetchall()
        agents = []
        for r in rows:
            total = (r.success_count or 0) + (r.failure_count or 0)
            accuracy = round((r.success_count or 0) / total * 100, 1) if total > 0 else 0.0
            agents.append({
                "id": r.agent_name,
                "name": r.agent_name,
                "strategy": r.tier or "Standard",
                "performance": f"+{accuracy}%",
                "accuracy": accuracy,
                "status": "Active",
                "color": "bg-secondary",
                "recommendation_count": total,
            })
        return {"status": "success", "data": agents}
    except Exception as e:
        logger.error(f"Error fetching agent status: {e}")
        # Fallback: return empty list instead of 500
        return {"status": "success", "data": []}

@dashboard_router.get("/alerts")
async def get_recent_alerts(user: Dict[str, Any] = Depends(get_current_user)):
    """獲取最新系統事件（用於 Dashboard 通知面板）"""
    try:
        from src.data.database import get_db_engine
        engine = get_db_engine()
        with engine.connect() as conn:
            rows = conn.execute(
                text("SELECT event_type, content, created_at FROM event_logs ORDER BY created_at DESC LIMIT 5")
            ).fetchall()
        alerts = [{"type": r.event_type, "msg": r.content, "time": str(r.created_at)[:16]} for r in rows]
        return {"status": "success", "data": alerts or []}
    except Exception as e:
        logger.error(f"Error fetching recent alerts: {e}")
        return {"status": "success", "data": []}

@dashboard_router.delete("/alerts")
async def clear_recent_alerts(user: Dict[str, Any] = Depends(get_current_user)):
    """清空/封存所有系統事件"""
    try:
        from src.data.database import get_db_engine
        engine = get_db_engine()
        user_id = user.get("sub")
        
        with engine.begin() as conn:
            if user_id:
                conn.execute(
                    text("DELETE FROM event_logs WHERE user_id = :uid"),
                    {"uid": user_id}
                )
            else:
                conn.execute(text("DELETE FROM event_logs"))
                
        return {"status": "success", "message": "所有通知已封存"}
    except Exception as e:
        logger.exception("Error clearing alerts")
        raise HTTPException(status_code=500, detail="Alert database maintenance failed")

@dashboard_router.post("/data/upload-csv")
async def upload_csv(
    file: UploadFile = File(...),
    user: Dict[str, Any] = Depends(get_current_user)
):
    """批次匯入 CSV 交易紀錄"""
    try:
        user_id = user.get("sub") or "default_user"
        content = await file.read()
        df = pd.read_csv(io.BytesIO(content))
        
        # 基礎欄位驗證
        required_cols = ["date", "ticker", "action", "quantity", "price"]
        for col in required_cols:
            if col not in df.columns:
                raise HTTPException(status_code=400, detail=f"遺失必要欄位: {col}")
        
        trans_service = TransactionService(user_id=user_id)
        count = 0
        for _, row in df.iterrows():
            try:
                # 轉換為服務需要的參數格式
                await trans_service.create_transaction(
                    ticker=str(row["ticker"]).upper(),
                    action=str(row["action"]).upper(),
                    quantity=float(row["quantity"]),
                    price=float(row["price"]),
                    fees=float(row.get("fees", 0)),
                    trade_date=str(row["date"])
                )
                count += 1
            except Exception as row_err:
                logger.warning(f"Failed to import row: {row_err}")
                continue

        return {"status": "success", "message": f"成功匯入 {count} 筆交易紀錄"}
    except Exception as e:
        logger.exception("CSV upload error")
        if isinstance(e, HTTPException): raise e
        raise HTTPException(status_code=500, detail="Bulk import processing failed")
