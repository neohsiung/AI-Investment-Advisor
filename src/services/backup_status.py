"""Freshness probe for the nightly backup status file written by scripts/backup_db.sh.
夜間備份狀態檔的新鮮度探針（狀態檔由 scripts/backup_db.sh 寫入）。

The worker mounts ./config read-only but not ./backups, so the script leaves its verdict in
``config/.backup_status.json``. Missing, unreadable, failed or old are all reported as a breach; none of them is ever
read as fine. / worker 看不到 ./backups，所以腳本把結果寫在 config/；讀不到、失敗、過舊一律回報，不當成正常。
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

BACKUP_STATUS_PATH = Path(__file__).resolve().parents[2] / "config" / ".backup_status.json"
# Nightly job + one missed-run margin; the weekly digest uses a coarser 2-day flag.
# 每晚一次加一次缺席的餘裕；週報用較粗的 2 天標記。
BACKUP_MAX_AGE_HOURS = 36


def probe(now: Optional[datetime] = None, path: Optional[Path] = None) -> Tuple[bool, str, str]:
    """Returns (ok, detail, severity). severity is 'critical' for a failed or stale backup (the file proves it) and
    'warning' when the status is simply unknown (no file yet, e.g. before the first run of the new script).
    回傳 (是否正常, 說明, 嚴重度)：失敗或過舊為 critical（有檔為證）；讀不到狀態則為 warning。"""
    now = now or datetime.now(timezone.utc)
    p = path or BACKUP_STATUS_PATH
    try:
        st = json.loads(p.read_text(encoding="utf-8"))
        at = datetime.fromisoformat(str(st["at"]).replace("Z", "+00:00"))
        ok = bool(st["ok"])
        reason = str(st.get("reason") or "")
    except FileNotFoundError:
        return False, "backup status file not found (backup never ran with the status-writing script?)", "warning"
    except Exception as e:  # noqa: BLE001 - reported to the caller as a breach, not swallowed
        logger.warning("backup status unreadable: %s", type(e).__name__)
        return False, f"backup status unreadable ({type(e).__name__})", "warning"
    age_h = (now - at).total_seconds() / 3600.0
    if not ok:
        return False, f"last backup FAILED {age_h:.1f}h ago: {reason or 'no reason recorded'}", "critical"
    if age_h > BACKUP_MAX_AGE_HOURS:
        return False, f"last successful backup is {age_h:.1f}h old (limit {BACKUP_MAX_AGE_HOURS}h)", "critical"
    return True, f"last backup ok {age_h:.1f}h ago", "warning"
