"""Daily Celery shell of the charter change engine (G6). The only charter module allowed to read the wall clock.
章程變更引擎的每日 Celery 外殼；章程模組中唯一可讀牆上時鐘者。

0-LLM. Ships in dry_run (charter_state.mode): it records verdicts and changes no live value. All decisions live in
src/services/parameter_engine.py.
"""
import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from src.config.owner import resolve_user_id
from src.data.database import get_db_engine
from src.infrastructure.celery_app import app
from src.services import charter_digest_service, parameter_engine
from src.services.market_data_service import MarketDataService
from src.services.notification_service import NotificationService
from src.services.settings_service import SettingsService

logger = logging.getLogger(__name__)

_TITLES = {
    "apply": "⚙️ 章程引擎套用參數變更 / Charter engine applied a change",
    "rollback": "↩️ 章程引擎回滾放寬 / Charter engine rolled back a loosening",
    "degrade": "🛑 章程引擎降級為僅收緊 / Charter engine degraded to tighten-only",
}


def _closes(user_id: str):
    """SPY closes for the regime proxy; a missing payload raises so the engine marks regime not measurable."""
    svc = MarketDataService(user_id=user_id)
    return lambda ticker, days=None: svc.get_ohlcv(ticker, days=days)["close"]


def _notifier(user_id: str):
    """Immediate notification for apply / rollback / degrade only. A send failure is logged, never fatal."""
    def notify(kind: str, **detail: Any) -> None:
        try:
            noti = NotificationService.create_with_settings(
                settings_service=SettingsService(user_id=user_id), user_id=user_id)
            body = "\n".join(f"{k}: {v}" for k, v in detail.items())
            asyncio.run(noti.notify_all(_TITLES.get(kind, kind), body, user_id=user_id, category="trading"))
        except Exception as e:
            logger.error("charter notification %s failed: %s", kind, e)
    return notify


@app.task(name="src.workflow.charter_tasks.run_parameter_engine", soft_time_limit=600, time_limit=660)
def run_parameter_engine(user_id: Optional[str] = None, now: Optional[datetime] = None) -> Dict[str, Any]:
    """Daily engine pass; beat calls it without arguments (``now`` exists so a test can fix the clock). / beat 不帶參數呼叫。"""
    user_id = resolve_user_id(user_id)
    now = now or datetime.now(timezone.utc)
    engine = get_db_engine()
    try:
        verdicts = parameter_engine.run_once(user_id, engine, now, notify=_notifier(user_id),
                                             closes_provider=_closes(user_id))
    except Exception as e:
        logger.warning("run_parameter_engine failed: %s", e, exc_info=True)
        try:
            parameter_engine.record_event(engine, user_id, "verdict", None, {"error": str(e)}, now)
        except Exception as e2:
            logger.error("run_parameter_engine: could not record the error event: %s", e2)
        return {"error": str(e), "verdicts": 0, "applied": 0}
    applied = sum(v.applied for v in verdicts)
    logger.info("run_parameter_engine: verdicts=%d applied=%d", len(verdicts), applied)
    return {"verdicts": len(verdicts), "applied": applied}


@app.task(name="src.workflow.charter_tasks.run_charter_weekly_digest", soft_time_limit=300, time_limit=360)
def run_charter_weekly_digest(user_id: Optional[str] = None, now: Optional[datetime] = None) -> Dict[str, Any]:
    """Saturday charter digest (G8); one row per ISO week. beat calls it without arguments. / 週六週報；每週一筆。"""
    user_id = resolve_user_id(user_id)
    now = now or datetime.now(timezone.utc)
    try:
        return charter_digest_service.write_weekly_digest(get_db_engine(), user_id, now)
    except Exception as e:
        logger.warning("run_charter_weekly_digest failed: %s", e, exc_info=True)
        return {"error": str(e), "written": False}
