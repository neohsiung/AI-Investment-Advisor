from typing import Optional, Any, Dict, List, Tuple
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

    def get_all_settings(self) -> Dict[str, str]:
        """
        Retrieves all settings from the database for the current user.
        為目前使用者從資料庫檢索所有設定。
        """
        settings = {}
        target_uid = self.user_id or 'SYSTEM'
        
        try:
            rows = self.settings_repo.get_all(target_uid)
            
            for key, value in rows:
                # v4.1.1: Auto-decode JSON strings if they look like JSON
                import json
                if isinstance(value, str):
                    if value.startswith(('{', '[')):
                        try:
                            settings[key] = json.loads(value)
                        except json.JSONDecodeError:
                            settings[key] = value
                    else:
                        settings[key] = value
                else:
                    settings[key] = value
        except Exception as e:
            print(f"Error loading settings: {e}")
            
        return settings

    def get_setting(self, key: str, default: Any = None) -> Any:
        """
        Retrieves a single setting value by its key.
        根據鍵值檢索單一設定值。
        """
        target_uid = self.user_id or 'SYSTEM'
        try:
            val = self.settings_repo.get(target_uid, key, default)
            
            import json
            if isinstance(val, str) and val.startswith(('{', '[')):
                try:
                    return json.loads(val)
                except json.JSONDecodeError:
                    pass
            return val
        except Exception:
            return default

    def save_setting(self, key: str, value: Any) -> Tuple[bool, str]:
        """
        Saves or updates a single setting in the database.
        在資料庫中儲存或更新單一設定。
        """
        try:
            target_uid = self.user_id or 'SYSTEM'
            self.settings_repo.set(target_uid, key, value)
            return True, "Success"
        except Exception as e:
            return False, str(e)

    def save_settings_bulk(self, settings_dict: Dict[str, Any]) -> Tuple[bool, str]:
        """
        Saves or updates multiple settings in a single transaction.
        在單一事務中儲存或更新多個設定。
        """
        try:
            target_uid = self.user_id or 'SYSTEM'
            for key, value in settings_dict.items():
                self.settings_repo.set(target_uid, key, value)
            return True, "Settings saved successfully."
        except Exception as e:
            return False, f"Error saving settings: {e}"

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
