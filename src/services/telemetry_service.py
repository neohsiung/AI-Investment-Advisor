"""
TelemetryService — opt-in product analytics (Loop 3, B-P3.2).

No feature-usage signal exists anywhere in this codebase, so there is no
way to know which parts of the product actually get used. This is
intentionally minimal: a feature name + small props dict, gated by a
per-user setting that defaults OFF for self-host (privacy-first) and
would default ON for the future managed-cloud offering. Never call
track() with financial figures, tickers, or any PII in props — event
names and coarse categorical props only.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class TelemetryService:
    def __init__(self, user_id: str):
        self.user_id = user_id

    def is_enabled(self) -> bool:
        try:
            from src.services.settings_service import SettingsService
            svc = SettingsService(user_id=self.user_id)
            value = svc.get_setting("telemetry_enabled", default=False, user_id=self.user_id)
            return str(value).lower() in ("true", "1")
        except Exception as e:
            logger.debug(f"Telemetry: is_enabled check failed, defaulting to disabled: {e}")
            return False

    def track(self, event: str, props: Optional[Dict[str, Any]] = None) -> None:
        """Fire-and-forget. No-op (not even a DB round-trip) unless the
        user has opted in."""
        if not self.is_enabled():
            return
        try:
            import json
            from sqlalchemy import text
            from src.data.database import get_db_engine
            engine = get_db_engine()
            with engine.begin() as conn:
                conn.execute(
                    text("INSERT INTO product_events (user_id, event, props) VALUES (:uid, :event, CAST(:props AS jsonb))"),
                    {"uid": self.user_id, "event": event, "props": json.dumps(props or {})},
                )
        except Exception as e:
            logger.debug(f"Telemetry: track({event}) failed (non-blocking): {e}")
