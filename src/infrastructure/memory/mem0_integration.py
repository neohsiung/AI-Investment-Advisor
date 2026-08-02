from typing import Dict, Any, List, Optional
from src.services.settings_service import SettingsService
from src.utils.logger import setup_logger

logger = setup_logger("Mem0Integration")

class Mem0UserPreferenceMemory:
    """
    Personalized User Preference Memory Layer inspired by Mem0.
    個人化 Agent 使用者偏好記憶層。
    """
    def __init__(self, user_id: str, settings_service: Optional[SettingsService] = None):
        self.user_id = user_id
        self.settings_service = settings_service or SettingsService(user_id=user_id)

    def extract_and_store_preference(self, key: str, value: Any) -> bool:
        """
        Stores structured user preference into persistent DB.
        """
        try:
            ok, msg = self.settings_service.save_setting(key, value, user_id=self.user_id)
            if ok:
                logger.info(f"Mem0 Memory updated: {key} = {value} for user {self.user_id}")
            return ok
        except Exception as e:
            logger.error(f"Failed to extract and store preference: {e}")
            return False

    def get_user_profile_summary(self) -> Dict[str, Any]:
        """
        Retrieves user risk profile, broker mode, confidence thresholds for Agent reasoning.
        """
        try:
            all_settings = self.settings_service.get_all_settings(user_id=self.user_id)
            return {
                "user_id": self.user_id,
                "auto_trade_threshold": all_settings.get("auto_trade_threshold", 75),
                "auto_trade_min_threshold": all_settings.get("auto_trade_min_threshold", 30),
                "risk_profile": all_settings.get("risk_profile", "Moderate"),
                "etoro_mode": all_settings.get("etoro_mode", "demo"),
                "enable_etoro": all_settings.get("enable_etoro", True),
                "target_cash_ratio": all_settings.get("target_cash_ratio", 0.20),
            }
        except Exception as e:
            logger.error(f"Failed to get user profile summary: {e}")
            return {"user_id": self.user_id, "risk_profile": "Moderate"}
