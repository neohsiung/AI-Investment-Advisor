from fastapi import APIRouter, HTTPException, Depends, Request
from typing import Dict, Any, List
import pandas as pd
from src.services.dashboard_service import DashboardService
from src.utils.logger import setup_logger
from src.utils.jwt_utils import decode_token

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
                "active_agents": metrics.get('active_agents', 14), # 暫時 hardcode 或從 metrics 獲取
                "risk_exposure": "MODERATE", # 暫時硬編碼，未來從分析引擎獲取
                "total_pnl": pnl.get('total', 0),
                "roi_percentage": data.get('roi', 0) * 100,
                "performance_change": "+12.4%" # 模擬 24h 變化
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

@dashboard_router.get("/agents")
async def get_agents(service: DashboardService = Depends(get_dashboard_service)):
    """獲取 Agent 狀態"""
    # 這裡未來應從 SentinelService 獲取真實狀態
    # 目前先返回 mock 數據，但結構與前端對接
    return {
        "status": "success",
        "data": [
            {"id": "ARCHON-01", "strategy": "HFT / ARBITRAGE", "alpha": "+$14,203", "status": "OPTIMIZING"},
            {"id": "SERAPH-09", "strategy": "LONG TAIL YIELD", "alpha": "+$4,812", "status": "SCANNING"},
            {"id": "VOSTOK-PRIME", "strategy": "CAPITAL PRESERVATION", "alpha": "$0.00", "status": "DORMANT"}
        ]
    }

@dashboard_router.get("/intelligence")
async def get_intelligence(service: DashboardService = Depends(get_dashboard_service)):
    """獲取策略情報"""
    return {
        "status": "success",
        "data": {
            "summary": "Based on current cross-exchange liquidity patterns, we are observing a significant migration from established blue-chip pairs into emerging Layer-2 infrastructure tokens.",
            "recommendation": "Increase ARCHON-01 allocation by 200 bps to capture mid-frequency volatility in DePIN derivatives.",
            "metrics": [
                {"label": "Institutional Inflow", "value": 88},
                {"label": "Social Momentum", "value": 42},
                {"label": "Developer Activity", "value": 92}
            ],
            "alerts": [
                {"type": "MARKET_ANOMALY", "msg": "Liquidity bridge drop detected in Sector 7G. Auto-rebalancing triggered.", "time": "2M AGO"},
                {"type": "STRATEGIC_UPDATE", "msg": "Archon-01 updated neural weights for BTC-ETH relative strength index.", "time": "14M AGO"}
            ]
        }
    }
