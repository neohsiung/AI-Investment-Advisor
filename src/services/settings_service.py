import typing
from typing import List, Dict, Tuple, Any, Optional, Callable, Dict, List, Tuple, Any, Optional, Callable
import requests
import pandas as pd
from src.repositories.settings_repository import AlchemySettingsRepository, ISettingsRepository
from src.repositories.prompt_repository import AlchemyPromptRepository, IPromptRepository

class SettingsService:
    """
    Service for managing user and system settings in the database.
    管理資料庫中使用者與系統設定的服務。
    """
    def __init__(self, db_path: str = None, user_id: str = None, 
                 settings_repo: ISettingsRepository = None, 
                 prompt_repo: IPromptRepository = None):
        """
        Initialize the settings service with repositories.
        初始化具備儲存庫的設定服務。
        """
        self.db_path = db_path
        self.user_id = user_id
        self.settings_repo = settings_repo or AlchemySettingsRepository()
        self.prompt_repo = prompt_repo or AlchemyPromptRepository()

    def _get_effective_uid(self) -> str:
        """
        Determine the effective user ID.
        """
        if not self.user_id:
            raise ValueError("SettingsService: No user_id provided or initialized.")
        return self.user_id

    def get_all_settings(self) -> Dict[str, str]:
        """
        Retrieves all settings from the database for the current user.
        """
        settings = {}
        target_uid = self._get_effective_uid()
        
        try:
            # v4.3.0: Strictly fetch only current user settings. No SYSTEM fallback.
            rows = self.settings_repo.get_all(target_uid)
            
            for key, value in rows:
                settings[key] = self._parse_setting_value(value)
        except Exception as e:
            print(f"Error loading settings: {e}")
            
        return settings

    def _parse_setting_value(self, value: Any) -> Any:
        """
        Parses a setting value from its raw database representation.
        """
        if value is None:
            return None
            
        import json
        if isinstance(value, str):
            # v4.3.1: Special handling for double-quoted string literals in DB
            if value.startswith('"') and value.endswith('"') and len(value) >= 2:
                try:
                    loaded = json.loads(value)
                    if isinstance(loaded, str):
                         return self._parse_setting_value(loaded) # Recurse once
                    return loaded
                except (json.JSONDecodeError, TypeError):
                    pass
                    
            if value.startswith(('{', '[')):
                try:
                    return json.loads(value)
                except (json.JSONDecodeError, TypeError):
                    return value
            
            # Handle standard literals
            if value.lower() == 'true': return True
            if value.lower() == 'false': return False
            if value.lower() == 'none': return None
            
        return value

    def get_setting(self, key: str, default: Any = None, user_id: str = None) -> Any:
        """
        Retrieves a single setting value by its key.
        v4.3.3: Strict DB-only retrieval per user policy.
        """
        target_uid = user_id or self._get_effective_uid()
        try:
            val = self.settings_repo.get(target_uid, key, default)
            return self._parse_setting_value(val)
        except Exception:
            return default

    def save_setting(self, key: str, value: Any, user_id: str = None) -> Tuple[bool, str]:
        """
        Saves or updates a single setting in the database.
        """
        try:
            target_uid = user_id or self._get_effective_uid()
            self.settings_repo.set(target_uid, key, value)
            return True, "Success"
        except Exception as e:
            return False, str(e)

    def save_settings_bulk(self, settings_dict: Dict[str, Any]) -> Tuple[bool, str]:
        """
        Saves or updates multiple settings in a single transaction.
        """
        try:
            target_uid = self._get_effective_uid()
            for key, value in settings_dict.items():
                self.settings_repo.set(target_uid, key, value)
            return True, "Settings saved successfully."
        except Exception as e:
            return False, f"Error saving settings: {e}"

    def delete_setting(self, key: str, user_id: str = None) -> Tuple[bool, str]:
        """
        Deletes a single setting from the database.
        """
        try:
            target_uid = user_id or self._get_effective_uid()
            success = self.settings_repo.delete(target_uid, key)
            if success:
                return True, "Setting deleted successfully."
            return False, "Setting not found."
        except Exception as e:
            return False, str(e)

    def fetch_openrouter_models(self) -> List[str]:
        """
        Fetches the list of available models from the OpenRouter API.
        從 OpenRouter API 獲取可用模型列表。
        """
        try:
            response = requests.get("https://openrouter.ai/api/v1/models", timeout=10)
            if response.status_code == 200:
                data = response.json()
                return sorted([model["id"] for model in data.get("data", [])])
            else:
                return []
        except Exception as e:
            print(f"Error fetching OpenRouter models: {e}")
            return []

    def get_prompt_history(self, user_id: str, limit: int = 50) -> pd.DataFrame:
        """
        Retrieves the history of prompt optimizations for a user.
        檢索使用者的提示詞優化歷史記錄。
        """
        try:
            return self.prompt_repo.get_history(user_id, limit)
        except Exception as e:
            print(f"Error reading prompt history: {e}")
            return pd.DataFrame()

    def find_user_by_channel_id(self, channel_id: str) -> Optional[str]:
        """
        Find an internal user ID (email) based on a channel-specific ID (e.g., LINE/Telegram).
        根據特定管道 ID（如 LINE/Telegram）尋找內部使用者 ID（電子郵件）。
        """
        try:
            return self.settings_repo.find_user_by_channel_id(channel_id)
        except Exception as e:
            print(f"Error in find_user_by_channel_id: {e}")
            return None

    def get_channel_ids_for_user(self, user_id: str) -> Dict[str, str]:
        """
        Get all channel IDs mapped to an internal user.
        """
        try:
            return self.settings_repo.get_channel_ids_for_user(user_id)
        except Exception as e:
            print(f"Error in get_channel_ids_for_user: {e}")
            return {}

    def find_user_by_webhook_secret(self, secret: str) -> Optional[str]:
        """
        Find an internal user ID (email/UUID) based on a webhook secret / API key.
        """
        try:
            return self.settings_repo.find_user_by_webhook_secret(secret)
        except Exception as e:
            print(f"Error in find_user_by_webhook_secret: {e}")
            return None

    def seed_sentinel_defaults(self, user_id: str = None) -> None:
        """
        Seed default priority handling times for the Sentinel system.
        """
        target_uid = user_id or self.user_id
        if not target_uid:
            return
            
        defaults = {
            "sentinel_p1_limit_mins": 15,
            "sentinel_p2_limit_mins": 60,
            "sentinel_p3_limit_mins": 240,
            "sentinel_p4_limit_mins": 720,
            "sentinel_p5_limit_mins": 1440
        }
        
        for key, val in defaults.items():
            self.save_setting(key, val, user_id=target_uid)
        
        print(f"SettingsService: Seeded sentinel priority defaults for user {target_uid}")
