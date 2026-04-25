from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from typing import List, Dict, Any
import httpx
import os
from src.api.v1.router import get_current_user_id
from src.api.v1.schemas.settings_schemas import (
    AllSettingsResponse, SettingsBulkSaveRequest, 
    ModelListResponse, NotificationTestRequest, StandardActionResponse
)
from src.services.settings_service import SettingsService
from src.utils.logger import setup_logger

logger = setup_logger("API_Settings")
router = APIRouter()

def get_settings_service(user_id: str = Depends(get_current_user_id)) -> SettingsService:
    return SettingsService(user_id=user_id)

@router.get("", response_model=AllSettingsResponse)
async def get_all_settings(service: SettingsService = Depends(get_settings_service)):
    """獲獲取使用者的所有系統設定 (若為空則自動從系統遷移或初始化預設值)"""
    try:
        settings = service.get_all_settings()
        
        # v4.4.1: 自動修復登入後設定空白或缺漏的問題
        if "AI_MODEL" not in settings or "auto_trade_threshold" not in settings:
            logger.info(f"Settings missing core keys for user {service.user_id}, triggering migration/initialization.")
            service.initialize_user_settings()
            # 重新取得初始化後的資料
            settings = service.get_all_settings()
            
        return {
            "status": "success",
            "data": settings
        }
    except Exception as e:
        logger.error(f"Error fetching settings: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("", response_model=StandardActionResponse)
async def save_settings(
    payload: SettingsBulkSaveRequest,
    background_tasks: BackgroundTasks,
    service: SettingsService = Depends(get_settings_service),
):
    """批次儲存系統設定 (非同步背景處理)"""
    try:
        background_tasks.add_task(service.save_settings_bulk, payload.settings)
        return {"status": "success", "message": "設定已收悉，系統正在背景更新中。"}
    except Exception as e:
        logger.error(f"Error saving settings: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/models", response_model=ModelListResponse)
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

@router.post("/test-notification", response_model=StandardActionResponse)
async def test_notification(
    payload: NotificationTestRequest,
    user_id: str = Depends(get_current_user_id)
):
    """發送測試通知至指定管道 (Telegram, LINE, Email)"""
    try:
        NOTIFY_SERVICE_URL = os.getenv("NOTIFY_SERVICE_URL", "http://notification:8001/api/v1/notify")
        
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(NOTIFY_SERVICE_URL, json={
                "user_id": user_id,
                "title": "🧪 Quantum AI 系統測試",
                "content": "如果您看到這則訊息，代表您的通知管道配置成功！",
                "channels": payload.channels,
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
        if isinstance(e, HTTPException): raise e
        raise HTTPException(status_code=500, detail=f"發送失敗: {str(e)}")
