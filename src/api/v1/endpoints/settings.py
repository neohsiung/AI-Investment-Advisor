from fastapi import APIRouter, Depends, HTTPException
from typing import List, Dict, Any
import httpx
import os
from src.api.v1.dependencies import get_current_user_id
from src.api.v1.schemas.settings_schemas import (
    AllSettingsResponse, SettingsBulkSaveRequest,
    ModelListResponse, NotificationTestRequest, StandardActionResponse,
    SettingsSchemaResponse, SettingsValidateResponse,
    CostProfileApplyRequest, CostProfilesResponse,
    OnboardingStatusResponse, OnboardingCompleteRequest,
)
from src.config.settings_schema import load_schema
from src.services.settings_service import SettingsService
from src.services.cost_profile_service import CostProfileService
from src.services.llm_provider_service import LLMProviderService
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
            # Two different failures, two different responses.
            #
            # Validation failures are the CALLER's error and their detail is
            # safe to return: the message is composed from schema metadata (key
            # names, declared bounds, enum members) and never from exception
            # text. A schema-driven form cannot show field-level errors if the
            # server refuses to say which key was wrong.
            #
            # Everything else keeps the original opaque 500. That message may be
            # derived from a DB/driver exception, and returning it is the
            # CWE-209 leak the 2026-08-02 fix closed — so it stays in the log.
            #
            # 驗證失敗屬呼叫端錯誤，且訊息僅由 schema 中介資料組成，可安全回傳，
            # 否則表單無法顯示欄位層級錯誤。其餘失敗維持不透明的 500，
            # 因其訊息可能源自資料庫例外（CWE-209）。
            if message.startswith("SETTINGS_VALIDATION_FAILED"):
                logger.warning(
                    "Rejected settings write for %s: %s", service.user_id, message
                )
                raise HTTPException(
                    status_code=400,
                    detail=message.split(": ", 1)[1] if ": " in message else message,
                )
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


@router.get("/schema", response_model=SettingsSchemaResponse)
async def get_settings_schema(service: SettingsService = Depends(get_settings_service)):
    """
    The field registry that drives the settings UI.

    This is what replaced 1030 lines of hand-written JSX: the frontend renders
    whatever this returns, so adding a knob is a YAML edit with no TypeScript
    change and no rebuild.

    Secret fields never carry their value — only `has_value`, so the form can
    show "configured" without the credential crossing the wire. That is why the
    UI cannot simply read GET /settings for secrets.

    此端點取代了 1030 行手寫 JSX：前端依回傳內容渲染，新增設定只需改 YAML。
    secret 欄位只回傳是否已設定，憑證不經過網路。
    """
    try:
        schema = load_schema()
        stored = service.get_all_settings()

        groups = []
        for group in schema.by_group():
            fields = []
            for f in group["fields"]:
                raw = stored.get(f.key)
                has_value = raw not in (None, "")
                fields.append({
                    "key": f.key,
                    "type": f.type,
                    "label_en": f.label_en,
                    "label_zh": f.label_zh,
                    "help_en": f.help_en,
                    "help_zh": f.help_zh,
                    # A secret's default is never interesting and its value must
                    # not leave the server.
                    "default": None if f.secret else f.default,
                    "enum": f.enum,
                    "min": f.minimum,
                    "max": f.maximum,
                    "secret": f.secret,
                    "danger": f.danger,
                    "restart": f.restart,
                    "depends": f.depends,
                    "has_value": has_value,
                })
            groups.append({
                "id": group["id"],
                "label_en": group["label_en"],
                "label_zh": group["label_zh"],
                "fields": fields,
            })

        return {"status": "success", "version": schema.version, "groups": groups}
    except Exception as e:
        logger.error(f"Error building settings schema: {e}")
        raise HTTPException(status_code=500, detail="Failed to load settings schema")


@router.post("/validate", response_model=SettingsValidateResponse)
async def validate_settings(
    payload: SettingsBulkSaveRequest,
    service: SettingsService = Depends(get_settings_service),
):
    """
    Dry-run the same validation `POST /settings` applies, without writing.

    Lets the form check a value before the operator commits it — relevant here
    because several of these keys move real money (order thresholds, capital
    caps, the trading kill switch).

    以與寫入端點相同的規則試算但不落地；此處多個鍵直接影響真實下單。
    """
    _, rejected = service._validate_against_schema(payload.settings or {})
    return {"status": "success", "valid": not rejected, "errors": rejected}


# ─────────────────────────────────────────────────────────────────────────────
# Cost Profiles & Onboarding Wizard Endpoints
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/cost-profiles", response_model=CostProfilesResponse)
async def get_cost_profiles(user_id: str = Depends(get_current_user_id)):
    """獲取可用的運算成本方案 (Frugal / Balanced / Aggressive) 與目前啟用的方案。"""
    try:
        service = CostProfileService(user_id=user_id)
        current = service.get_current_profile()
        profiles = service.list_profiles()
        return {
            "status": "success",
            "active_profile": current["id"],
            "profiles": profiles,
        }
    except Exception as e:
        logger.error(f"Error getting cost profiles: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve cost profiles")


@router.post("/cost-profiles/apply", response_model=StandardActionResponse)
async def apply_cost_profile(
    payload: CostProfileApplyRequest,
    user_id: str = Depends(get_current_user_id),
):
    """套用選定的運算成本方案，調整哨兵週期與各項外部資訊抓取頻率。"""
    try:
        service = CostProfileService(user_id=user_id)
        res = service.apply_profile(payload.profile)
        return {
            "status": "success",
            "message": f"成本配置方案已成功切換為 {res['name']}。",
            "debug": res,
        }
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        logger.error(f"Error applying cost profile '{payload.profile}': {e}")
        raise HTTPException(status_code=500, detail="Failed to apply cost profile")


@router.get("/onboarding-status", response_model=OnboardingStatusResponse)
async def get_onboarding_status(user_id: str = Depends(get_current_user_id)):
    """檢查系統是否需要開箱引導 (是否有任何已配置憑證之 LLM Provider)。"""
    try:
        cost_service = CostProfileService(user_id=user_id)
        active_profile = cost_service.get_current_profile()["id"]

        provider_service = LLMProviderService(user_id=user_id)
        providers = provider_service.list()

        configured = []
        for p in providers:
            if not p.get("enabled"):
                continue
            has_key = bool(p.get("api_key_masked"))
            is_local = p.get("provider_code") == "ollama" and bool(p.get("base_url"))
            if has_key or is_local:
                configured.append(p["provider_code"])

        needs_onboarding = len(configured) == 0
        return {
            "status": "success",
            "needs_onboarding": needs_onboarding,
            "configured_providers": configured,
            "active_cost_profile": active_profile,
        }
    except Exception as e:
        logger.error(f"Error getting onboarding status: {e}")
        raise HTTPException(status_code=500, detail="Failed to check onboarding status")


@router.post("/onboarding/complete", response_model=StandardActionResponse)
async def complete_onboarding(
    payload: OnboardingCompleteRequest,
    user_id: str = Depends(get_current_user_id),
):
    """
    完成初始開箱設定：
    1. 套用選取的運算成本方案 (若有指定)。
    2. 設定並啟用指定之主要 LLM 提供商金鑰或端點。
    """
    try:
        # 1. 套用成本方案
        if payload.cost_profile:
            cost_service = CostProfileService(user_id=user_id)
            cost_service.apply_profile(payload.cost_profile)

        # 2. 配置提供商
        provider_service = LLMProviderService(user_id=user_id)
        providers = provider_service.list()

        existing = next((p for p in providers if p["provider_code"] == payload.provider_code), None)
        patch_data: Dict[str, Any] = {"enabled": True}
        if payload.api_key:
            patch_data["api_key"] = payload.api_key
        if payload.base_url:
            patch_data["base_url"] = payload.base_url

        if existing:
            provider_service.update(existing["id"], patch_data)
        else:
            # 建立新的 Provider 實例
            display_name = payload.provider_code.title()
            provider_service.create({
                "provider_code": payload.provider_code,
                "display_name": display_name,
                "api_key": payload.api_key,
                "base_url": payload.base_url,
                "enabled": True,
            })

        return {
            "status": "success",
            "message": "開箱設定已成功完成！系統已就緒。",
        }
    except Exception as e:
        logger.error(f"Error completing onboarding: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to complete onboarding: {e}")

