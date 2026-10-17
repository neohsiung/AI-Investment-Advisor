"""
Canonical gate for loops that tune live settings or register strategies from synthetic data.
以合成資料調整實盤設定或註冊策略之演化迴圈的規範閘門（settings family: ``evolution_gate``）。

Kept dependency-light so both Celery tasks and services share ONE definition; `force` never bypasses it.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

EVOLUTION_GATE_KEY = "enable_autonomous_evolution_beat"


def synthetic_evolution_enabled(user_id: str) -> bool:
    """
    Off unless `enable_autonomous_evolution_beat` is explicitly true; a read failure keeps it off (fail-closed)
    and is logged at warning level.
    除非明確開啟否則關閉；讀取失敗維持關閉並以 warning 記錄。
    """
    try:
        from src.services.settings_service import SettingsService
        val = SettingsService(user_id=user_id).get_setting(EVOLUTION_GATE_KEY, False)
        return val is True or str(val).lower() == "true"
    except Exception as e:
        logger.warning("%s unreadable for %s (%s); evolution stays off", EVOLUTION_GATE_KEY, user_id, e)
        return False
