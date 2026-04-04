from fastapi import APIRouter, HTTPException, Depends, Request, Body, UploadFile, File
from sqlalchemy import text
from typing import Dict, Any, List
import pandas as pd
import io
import re
import httpx
import os
from src.services.dashboard_service import DashboardService
from src.utils.logger import setup_logger
from src.utils.jwt_utils import decode_token
from src.services.performance_service import PerformanceService
from src.repositories.report_repository import AlchemyReportRepository
from src.agents.factory import AgentFactory
from src.services.transaction_service import TransactionService
from src.services.settings_service import SettingsService
from src.services.intelligence_service import IntelligenceService

logger = setup_logger("DashboardRouter")
dashboard_router = APIRouter(tags=["Dashboard"])

def get_current_user(request: Request) -> Dict[str, Any]:
    """從 Cookie 驗證 JWT 並獲取使用者資訊"""
    token = request.cookies.get("access_token")
    if not token:
        logger.warning("Missing access_token in cookies")
        raise HTTPException(status_code=401, detail="Not authenticated")
        
    payload = decode_token(token)
    if not payload or payload.get("type") != "access":
        logger.warning("Invalid or expired access_token")
        raise HTTPException(status_code=401, detail="Invalid token")
        
    return payload

def get_dashboard_service(user: Dict[str, Any] = Depends(get_current_user)) -> DashboardService:
    """獲取 DashboardService 實例，綁定當前使用者"""
    user_id = user.get("sub")
    from services.mcp_server.src.app.state import services
    
    # 注意：在真實多租戶環境，這裡應該按需創建服務或從池中獲取
    # 目前專案結構偏向單一 User 實例，我們檢查 services 中是否已有
    if "dashboard" in services and services["dashboard"].user_id == user_id:
        return services["dashboard"]
    
    # 若不匹配或未初始化，建立新實例 (或報錯)
    # 這裡為求穩定，我們先嘗試返回全域單例，若 user_id 不匹配則警告
    if "dashboard" in services:
        return services["dashboard"]
        
    raise HTTPException(status_code=503, detail="Dashboard service not ready")

def get_performance_service(user: Dict[str, Any] = Depends(get_current_user)) -> PerformanceService:
    """獲取 PerformanceService 實例"""
    user_id = user.get("sub")
    return PerformanceService(user_id=user_id)

def get_reports_repository(user: Dict[str, Any] = Depends(get_current_user)) -> AlchemyReportRepository:
    """獲取 AlchemyReportRepository 實例"""
    return AlchemyReportRepository()

@dashboard_router.get("/reports")
async def get_reports(repo: AlchemyReportRepository = Depends(get_reports_repository), user: Dict[str, Any] = Depends(get_current_user)):
    """獲取最新的投資分析報告"""
    try:
        user_id = user.get("sub", "demo_user")
        reports_df = repo.get_latest_reports(user_id=user_id)
        return {
            "status": "success",
            "data": reports_df.to_dict(orient='records')
        }
    except Exception as e:
        logger.error(f"Error fetching reports: {e}")
        raise HTTPException(status_code=500, detail=str(e))


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
        logger.error(f"Error fetching settings: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@dashboard_router.post("/settings")
async def save_settings(
    payload: Dict[str, Any] = Body(...),
    service: SettingsService = Depends(get_settings_service)
):
    """批次儲存系統設定"""
    try:
        success, msg = service.save_settings_bulk(payload)
        if not success:
            raise HTTPException(status_code=400, detail=msg)
        return {"status": "success", "message": msg}
    except Exception as e:
        logger.error(f"Error saving settings: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@dashboard_router.post("/settings/test-notification")
async def test_notification(
    payload: Dict[str, Any] = Body(...),
    user: Dict[str, Any] = Depends(get_current_user)
):
    """發送測試通知至指定管道 (Telegram, LINE, Email)"""
    try:
        user_id = user.get("sub")
        channels = payload.get("channels", ["telegram", "line"])
        
        # 內網呼叫 Notification 微服務
        # 在 Docker 環境中，主機名稱為 'notification'
        NOTIFY_SERVICE_URL = os.getenv("NOTIFY_SERVICE_URL", "http://notification:8001/api/v1/notify")
        
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(NOTIFY_SERVICE_URL, json={
                "user_id": user_id,
                "title": "🧪 Quantum AI 系統測試",
                "content": "如果您看到這則訊息，代表您的通知管道配置成功！",
                "channels": channels,
                "category": "test"
            })
            
            if resp.status_code >= 400:
                logger.error(f"Notification service returned error: {resp.status_code} - {resp.text}")
                raise HTTPException(status_code=resp.status_code, detail="通知服務暫時無法處理您的請求")
            
            return {
                "status": "success",
                "message": "測試通知已排入發送隊列",
                "debug": resp.json()
            }
            
    except Exception as e:
        logger.error(f"Error triggering test notification: {e}")
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(status_code=500, detail=f"發送失敗: {str(e)}")

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
        logger.error(f"Error fetching models: {e}")
        raise HTTPException(status_code=500, detail=str(e))

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
        logger.error(f"Error fetching transactions: {e}")
        raise HTTPException(status_code=500, detail=str(e))

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
            raise HTTPException(status_code=400, detail=msg)
            
        return {"status": "success", "message": msg}
    except Exception as e:
        logger.error(f"Error adding transaction: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@dashboard_router.delete("/data/transactions/{transaction_id}")
async def delete_transaction(
    transaction_id: str,
    service: TransactionService = Depends(get_transaction_service)
):
    """刪除特定的交易紀錄"""
    try:
        success, msg = service.delete_transaction(transaction_id)
        if not success:
            raise HTTPException(status_code=400, detail=msg)
            
        return {"status": "success", "message": msg}
    except Exception as e:
        logger.error(f"Error deleting transaction: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@dashboard_router.post("/chat")
async def advisor_chat(
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

        factory = AgentFactory()
        cio_agent = factory.create_cio_agent(user_id=user_id)

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

        # 調用 LLM
        response = cio_agent.call_llm(messages=messages, temperature=0.7)

        return {
            "status": "success",
            "data": {
                "message": response,
                "detected_ticker": ticker
            }
        }
    except Exception as e:
        logger.error(f"Chat error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@dashboard_router.get("/summary")
async def get_summary(service: DashboardService = Depends(get_dashboard_service)):
    """獲取投資概覽數據 (NLV, Cash, PnL, ROI)"""
    try:
        data = service.prepare_dashboard_data(service.user_id)
        metrics = data.get('metrics', {})
        pnl = data.get('pnl_data', {})
        
        return {
            "status": "success",
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
            }
        }
    except Exception as e:
        logger.error(f"Error fetching dashboard summary: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@dashboard_router.get("/positions")
async def get_positions(service: DashboardService = Depends(get_dashboard_service)):
    """獲取持倉清單"""
    try:
        data = service.prepare_dashboard_data(service.user_id)
        positions_df = data.get('positions_df', pd.DataFrame())
        
        if positions_df.empty:
            return {"status": "success", "data": []}
            
        return {
            "status": "success",
            "data": positions_df.to_dict(orient='records')
        }
    except Exception as e:
        logger.error(f"Error fetching positions: {e}")
        raise HTTPException(status_code=500, detail=str(e))

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
    """獲取 AI 生成的市場分析與情緒報告 (繁體中文)"""
    try:
        user_id = user.get("sub") or "default_user"
        intel_service = IntelligenceService(user_id=user_id)
        report = await intel_service.generate_briefing()
        return {
            "status": "success",
            "data": report
        }
    except Exception as e:
        logger.error(f"Intelligence generation error: {e}")
        # Return fallback data instead of 500 to keep UI stable
        return {
            "status": "success", 
            "data": {
                "executive_summary": "市場情報生成中，請稍候再試或檢查 API 金鑰配置。",
                "recommendation": "系統整合中",
                "ai_note": "ERROR_LOGGED",
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
        logger.error(f"Error fetching performance history: {e}")
        raise HTTPException(status_code=500, detail=str(e))

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
        logger.error(f"Error fetching agent performance: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@dashboard_router.get("/agents")
async def get_agent_status_list(user: Dict[str, Any] = Depends(get_current_user)):
    """獲取 Agent 運行狀態列表（從 agent_performance 表）"""
    try:
        from src.repositories.postgres_repositories import AlchemyAgentRepository
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
        from src.database import db
        rows = db.session.execute(
            text("SELECT event_type, message, created_at FROM event_logs ORDER BY created_at DESC LIMIT 5")
        ).fetchall()
        alerts = [{"type": r.event_type, "msg": r.message, "time": str(r.created_at)[:16]} for r in rows]
        return {"status": "success", "data": alerts or []}
    except Exception as e:
        logger.error(f"Error fetching recent alerts: {e}")
        return {"status": "success", "data": []}

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
        logger.error(f"CSV upload error: {e}")
        raise HTTPException(status_code=500, detail=f"處理 CSV 失敗: {str(e)}")
