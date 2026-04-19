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

    def get_all_settings(self, user_id: str = None) -> Dict[str, Any]:
        """
        Retrieves all settings from the database for the current user.
        """
        settings = {}
        target_uid = user_id or self._get_effective_uid()
        
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

    def initialize_user_settings(self, user_id: str = None) -> bool:
        """
        Ensures a user has at least default settings. 
        If no settings exist, it attempts to migrate from SYSTEM and seeds defaults.
        針對新用戶或遺失設定的用戶進行初始化。優先從 SYSTEM 遷移，否則給予軟代碼預設值。
        """
        target_uid = user_id or self.user_id
        if not target_uid:
            return False
            
        # B2C Safety Check: Ensure user exists in users table before creating settings
        # to avoid Foreign Key violations.
        from sqlalchemy import text
        try:
            with self.settings_repo.engine.connect() as conn:
                exists = conn.execute(
                    text("SELECT 1 FROM users WHERE id = :uid"), {"uid": target_uid}
                ).first()
            if not exists:
                import logging
                logging.getLogger("SettingsService").error(
                    f"Initialization aborted: User {target_uid!r} not found in users table."
                )
                return False
        except Exception as e:
            import logging
            logging.getLogger("SettingsService").error(f"Error checking user existence: {e}")
            return False
            
        # 1. 檢查是否已經「完全」初始化
        # 若已有關鍵設定，則視為已完全初始化
        existing = self.get_all_settings(user_id=target_uid)
        if "AI_MODEL" in existing and "auto_trade_threshold" in existing:
            return False # Core keys exist, no need to seed again
            
        # 2. 嘗試從 SYSTEM 帳號遷移舊有設定 (無縫升級)
        system_settings_found = False
        try:
            # Note: AlchemySettingsRepository.get_all 繞過了 _resolve_user 的 ValueError 檢查
            rows = self.settings_repo.get_all("SYSTEM")
            if not rows:
                 rows = self.settings_repo.get_all("system")
            
            if rows:
                for key, val in rows:
                    # 進行透明遷移
                    self.save_setting(key, val, user_id=target_uid)
                system_settings_found = True
                print(f"SettingsService: Migrated {len(rows)} settings from SYSTEM to {target_uid}")
        except Exception as e:
            print(f"SettingsService: Migration from SYSTEM failed: {e}")

        # 3. 填補基礎 UX 必備預設值 (若遷移後仍缺少的關鍵欄位)
        # NOTE: AI_MODEL_* 為舊路徑 (settings 表) 的 fallback 預設值。
        #       新路徑優先使用 llm_tier_bindings 表（由 AI Engine Management UI 管理）。
        #       模型名稱從 TierConfig.DEFAULT_TIERS 動態讀取，避免重複的真相來源。
        from src.infrastructure.llm.tier_config import TierConfig
        _tc = TierConfig()
        defaults = {
            "auto_trade_threshold": 75,
            "auto_trade_min_threshold": 30,
            "risk_profile": "Aggressive",
            "target_cash_ratio": 0.2,
            "AI_PROVIDER": "OpenRouter",
            "AI_MODEL":          _tc.resolve("smart"),    # smart tier fallback
            "AI_MODEL_ADVANCED": _tc.resolve("advanced"), # advanced tier fallback
            "AI_MODEL_SMART":    _tc.resolve("smart"),    # smart tier fallback
            "AI_MODEL_FAST":     _tc.resolve("fast"),     # fast tier fallback
            "AI_MODEL_NANO":     _tc.resolve("nano"),     # nano tier fallback
            "DISPLAY_TIMEZONE": "Asia/Taipei",
            "enable_etoro": False,
            "etoro_mode": "demo"
        }
        
        # 重新整理遷移後的現況
        updated_settings = self.get_all_settings(user_id=target_uid)
        
        for key, val in defaults.items():
            if key not in updated_settings:
                self.save_setting(key, val, user_id=target_uid)
        
        # 4. 賦予 Sentinel 系統預設頻率
        self.seed_sentinel_defaults(user_id=target_uid)
        
        print(f"SettingsService: User {target_uid} initialization complete.")
        return True
