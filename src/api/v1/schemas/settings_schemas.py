from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any

class SettingsItem(BaseModel):
    """Individual configuration key-value pair."""
    key: str
    value: Any
    category: Optional[str] = "general"

class AllSettingsResponse(BaseModel):
    """Standardized response for all system settings."""
    status: str = "success"
    data: Dict[str, Any]

class SettingsBulkSaveRequest(BaseModel):
    """
    Request schema for batch updating settings.

    Still `Dict[str, Any]` at the transport layer, deliberately: the valid keys
    and their types live in config/settings_schema.yaml, which is data, not code.
    Encoding them as pydantic fields here would mean a code change (and a deploy)
    to add a knob — the opposite of the point. Validation happens in
    SettingsService against the registry, and a failure comes back as 400 with
    the offending keys named.

    傳輸層刻意保持 Dict：合法鍵與型別定義在 YAML 註冊表中（資料，不是程式碼）。
    若在此寫成 pydantic 欄位，新增一個設定就得改程式並重新部署。
    """
    settings: Dict[str, Any]


class SettingsFieldSchema(BaseModel):
    """One renderable field. Mirrors a row of config/settings_schema.yaml."""
    key: str
    type: str
    label_en: str
    label_zh: str = ""
    help_en: str = ""
    help_zh: str = ""
    default: Any = None
    enum: Optional[List[Any]] = None
    min: Optional[float] = None
    max: Optional[float] = None
    secret: bool = False
    danger: bool = False
    restart: bool = False
    depends: Optional[str] = None
    # Secrets never carry a value; the UI shows a filled/empty state instead.
    # secret 欄位不回傳值，僅回傳是否已設定。
    has_value: bool = False


class SettingsGroupSchema(BaseModel):
    """A tab in the settings UI."""
    id: str
    label_en: str
    label_zh: str = ""
    fields: List[SettingsFieldSchema]


class SettingsSchemaResponse(BaseModel):
    status: str = "success"
    version: int
    groups: List[SettingsGroupSchema]


class SettingsValidateResponse(BaseModel):
    status: str = "success"
    valid: bool
    errors: List[str] = Field(default_factory=list)

class OpenRouterModel(BaseModel):
    """Representation of an AI model available via OpenRouter."""
    id: str
    name: str
    context_length: int
    pricing: Dict[str, Any]

class ModelListResponse(BaseModel):
    """Standardized response for available AI models."""
    status: str = "success"
    data: List[OpenRouterModel]

class NotificationTestRequest(BaseModel):
    """Request to send a test notification."""
    channels: List[str] = Field(default=["telegram", "line"], description="Channels to test (e.g., telegram, line, email)")

class StandardActionResponse(BaseModel):
    """Standard success message response."""
    status: str = "success"
    message: str
    debug: Optional[Dict[str, Any]] = None


class CostProfileApplyRequest(BaseModel):
    """Request to apply an operating cost profile."""
    profile: str = Field(..., description="Cost profile ID ('frugal', 'balanced', 'aggressive')")


class CostProfilesResponse(BaseModel):
    """List of all available cost profiles and the currently active profile."""
    status: str = "success"
    active_profile: str
    profiles: List[Dict[str, Any]]


class OnboardingStatusResponse(BaseModel):
    """Response indicating whether the system requires initial setup/onboarding."""
    status: str = "success"
    needs_onboarding: bool
    configured_providers: List[str]
    active_cost_profile: str


class OnboardingCompleteRequest(BaseModel):
    """Composite request to complete initial onboarding."""
    cost_profile: Optional[str] = Field("balanced", description="Selected cost profile")
    provider_code: str = Field("openrouter", description="Primary LLM provider code (e.g. openrouter, ollama)")
    api_key: Optional[str] = Field(None, description="API Key (required for cloud providers like OpenRouter)")
    base_url: Optional[str] = Field(None, description="Custom base URL (e.g. for Ollama)")

