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
    """Request schema for batch updating settings."""
    settings: Dict[str, Any]

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
