import logging
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.services.settings_service import SettingsService

logger = logging.getLogger(__name__)

COST_PROFILES: Dict[str, Dict[str, Any]] = {
    "frugal": {
        "id": "frugal",
        "name": "Frugal (節省型)",
        "description": "最低運算成本方案。每 30 分鐘執行哨兵掃描，優先採用 Nano/反射層輕量模型，延長外部資料抓取間隔。適合本機 Ollama 或個人精簡預算。",
        "estimated_weekly_cost": "~$2 – $5 USD (使用本機 Ollama 為 $0)",
        "sentinel_tick_minute": "*/30",
        "sentinel_breaking_news_interval_min": 60,
        "sentinel_macro_interval_min": 120,
        "sentinel_deep_interval_min": 180,
        "recommended_providers": ["ollama", "openrouter"],
    },
    "balanced": {
        "id": "balanced",
        "name": "Balanced (平衡型 - 推薦)",
        "description": "標準運作平衡方案。每 15 分鐘執行哨兵掃描，委員會辯論調用 Smart 階層模型，兼顧市場反應靈敏度與 API 費用控制。",
        "estimated_weekly_cost": "~$15 – $25 USD",
        "sentinel_tick_minute": "*/15",
        "sentinel_breaking_news_interval_min": 30,
        "sentinel_macro_interval_min": 60,
        "sentinel_deep_interval_min": 60,
        "recommended_providers": ["openrouter"],
    },
    "aggressive": {
        "id": "aggressive",
        "name": "Aggressive (積極型)",
        "description": "高頻市場監控方案。每 5 分鐘執行哨兵掃描，高頻更新全球總經與突發新聞，全面啟用 Smart/Advanced 深度推理階層。",
        "estimated_weekly_cost": "~$50 – $100 USD",
        "sentinel_tick_minute": "*/5",
        "sentinel_breaking_news_interval_min": 10,
        "sentinel_macro_interval_min": 30,
        "sentinel_deep_interval_min": 30,
        "recommended_providers": ["openrouter"],
    },
}

DEFAULT_PROFILE = "balanced"


class CostProfileService:
    """
    Manages operational cost profiles (Frugal, Balanced, Aggressive),
    coordinating sentinel tick cadences, data fetch intervals, and LLM budget allocation.
    """

    def __init__(self, user_id: Optional[str] = None, settings_service: Optional[SettingsService] = None):
        self.user_id = user_id
        self.settings_service = settings_service or SettingsService(user_id=user_id)

    @classmethod
    def list_profiles(cls) -> List[Dict[str, Any]]:
        """Return the list of all defined cost profiles."""
        return list(COST_PROFILES.values())

    @classmethod
    def get_profile(cls, profile_id: str) -> Optional[Dict[str, Any]]:
        """Get specification for a profile ID."""
        return COST_PROFILES.get(profile_id)

    def get_current_profile(self) -> Dict[str, Any]:
        """
        Determines the current cost profile for the user based on saved settings,
        defaulting to 'balanced' if not explicitly configured.
        """
        active_id = self.settings_service.get_setting("cost_profile")
        if not active_id or active_id not in COST_PROFILES:
            active_id = DEFAULT_PROFILE

        profile = dict(COST_PROFILES[active_id])
        profile["is_active"] = True
        return profile

    def apply_profile(self, profile_id: str, env_file_path: Optional[str] = None) -> Dict[str, Any]:
        """
        Apply a cost profile:
        1. Save settings (cost_profile, sentinel intervals) in the database.
        2. Sync SENTINEL_TICK_CRON_MINUTE into .env file if available.
        """
        if profile_id not in COST_PROFILES:
            raise ValueError(f"Unknown cost profile '{profile_id}'. Valid options: {list(COST_PROFILES.keys())}")

        spec = COST_PROFILES[profile_id]

        # 1. Update database settings
        settings_payload = {
            "cost_profile": profile_id,
            "sentinel_breaking_news_interval_min": spec["sentinel_breaking_news_interval_min"],
            "sentinel_macro_interval_min": spec["sentinel_macro_interval_min"],
            "sentinel_deep_interval_min": spec["sentinel_deep_interval_min"],
        }
        self.settings_service.save_settings_bulk(settings_payload)
        logger.info("Saved cost profile '%s' settings for user=%s", profile_id, self.user_id)

        # 2. Sync to .env file if it exists
        self._sync_env_file(spec["sentinel_tick_minute"], env_file_path)

        res = dict(spec)
        res["is_active"] = True
        return res

    def _sync_env_file(self, sentinel_tick_cron: str, env_file_path: Optional[str] = None) -> None:
        """Update SENTINEL_TICK_CRON_MINUTE in .env."""
        target_path = Path(env_file_path) if env_file_path else Path(".env")
        if not target_path.exists():
            # Try project root relative to this file
            target_path = Path(__file__).resolve().parent.parent.parent / ".env"

        if not target_path.exists():
            logger.debug("No .env found at %s to update SENTINEL_TICK_CRON_MINUTE", target_path)
            return

        try:
            content = target_path.read_text(encoding="utf-8")
            pattern = r"^SENTINEL_TICK_CRON_MINUTE=.*$"
            replacement = f'SENTINEL_TICK_CRON_MINUTE="{sentinel_tick_cron}"'

            if re.search(pattern, content, flags=re.MULTILINE):
                new_content = re.sub(pattern, replacement, content, flags=re.MULTILINE)
            else:
                new_content = content.rstrip() + f"\n{replacement}\n"

            target_path.write_text(new_content, encoding="utf-8")
            logger.info("Updated SENTINEL_TICK_CRON_MINUTE=%s in %s", sentinel_tick_cron, target_path)
        except Exception as e:
            logger.warning("Could not update %s with new SENTINEL_TICK_CRON_MINUTE: %s", target_path, e)
