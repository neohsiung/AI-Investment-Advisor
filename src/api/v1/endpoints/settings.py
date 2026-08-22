from fastapi import APIRouter, Depends, HTTPException
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
        if "AI_MODEL" not in settings or "auto_trade_threshold" not in settings or "webhook_api_key" not in settings:
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
        raise HTTPException(status_code=500, detail="Failed to fetch settings")

@router.post("", response_model=StandardActionResponse)
async def save_settings(
    payload: SettingsBulkSaveRequest,
    service: SettingsService = Depends(get_settings_service),
):
    """
    批次儲存系統設定 (同步寫入，200 代表已實際落地)。

    2026-08-02: was fire-and-forget via BackgroundTasks — the 200 returned
    before the write happened, save_settings_bulk's failure return value was
    discarded, and the frontend's immediate mutate() raced its own write. These
    are the most safety-critical writes in the system (broker credentials,
    trading mode, kill switch), so the caller must learn whether they landed.
    The work is a handful of indexed upserts; the backgrounding bought nothing.
    2026-08-02：原為背景寫入，200 不代表成功且前端會 race。這裡是券商憑證/交易模式/
    kill switch 等最關鍵的寫入，改為同步並回報真實結果。
    """
    try:
        ok, message = service.save_settings_bulk(payload.settings)
        if not ok:
            # Log the service's message; never return it. save_settings_bulk
            # now yields a stable code rather than exception text, and keeping
            # both the raise and the success return on fixed strings severs the
            # taint path twice so a future refactor cannot reopen it.
            # 訊息只進 log 不外流；raise 與成功回傳都用固定字串，斷兩次污染路徑。
            logger.error(f"Error saving settings for {service.user_id}: {message}")
            raise HTTPException(status_code=500, detail="Failed to save settings")
        return {"status": "success", "message": "設定已儲存。"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error saving settings: {e}")
        raise HTTPException(status_code=500, detail="Failed to save settings")

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
        raise HTTPException(status_code=500, detail="Failed to fetch available models")

@router.post("/test-notification", response_model=StandardActionResponse)
async def test_notification(
    payload: NotificationTestRequest,
    user_id: str = Depends(get_current_user_id)
):
    """直接通過 TelegramAdapter 發送測試通知"""
    results = {}
    
    # 延遲導入以避免循環依賴
    from src.infrastructure.channels.telegram_adapter import TelegramAdapter
    adapter = TelegramAdapter()
    
    for channel in payload.channels:
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
            # 目前僅支援 Telegram 測試
            results[channel] = False
    
    return {
        "status": "success",
        "message": "測試通知已發送",
        "debug": results
    }
