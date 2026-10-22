"""Nightly backup freshness alert (self_ops named check). / 夜間備份新鮮度告警。"""
import json
from datetime import datetime, timedelta, timezone

from src.services import backup_status
from src.services.self_ops_service import SelfOpsService, _NAMED_CHECKS

NOW = datetime(2026, 10, 22, 12, 0, tzinfo=timezone.utc)


def _write(tmp_path, ok=True, hours_ago=5.0, reason=""):
    p = tmp_path / "s.json"
    at = (NOW - timedelta(hours=hours_ago)).strftime("%Y-%m-%dT%H:%M:%SZ")
    p.write_text(json.dumps({"ok": ok, "file": "f.sql", "bytes": 10, "at": at, "reason": reason}))
    return p


def test_fresh_success_is_ok(tmp_path):
    ok, _, _ = backup_status.probe(NOW, _write(tmp_path))
    assert ok


def test_failure_is_critical_with_reason(tmp_path):
    ok, detail, sev = backup_status.probe(NOW, _write(tmp_path, ok=False, reason="dump is empty"))
    assert not ok and sev == "critical" and "dump is empty" in detail


def test_stale_success_is_critical(tmp_path):
    ok, detail, sev = backup_status.probe(NOW, _write(tmp_path, hours_ago=37))
    assert not ok and sev == "critical" and "37.0h" in detail


def test_boundary_36h_still_ok(tmp_path):
    ok, _, _ = backup_status.probe(NOW, _write(tmp_path, hours_ago=36))
    assert ok


def test_missing_file_is_warning_not_ok(tmp_path):
    ok, _, sev = backup_status.probe(NOW, tmp_path / "nope.json")
    assert not ok and sev == "warning"


def test_corrupt_file_is_warning_not_ok(tmp_path):
    p = tmp_path / "bad.json"
    p.write_text("{not json")
    ok, detail, sev = backup_status.probe(NOW, p)
    assert not ok and sev == "warning" and "JSONDecodeError" in detail


def test_named_check_wired_to_probe(tmp_path, monkeypatch):
    assert "probe" in _NAMED_CHECKS["nightly_backup_fresh"]
    monkeypatch.setattr(backup_status, "BACKUP_STATUS_PATH", _write(tmp_path, ok=False, reason="boom"))
    br = SelfOpsService(user_id="u")._check_named(None, "check:nightly_backup_fresh", "nightly_backup_fresh")
    assert br["severity"] == "critical" and "boom" in br["detail"]


def test_named_check_none_when_healthy(tmp_path, monkeypatch):
    fresh = datetime.now(timezone.utc) - timedelta(hours=1)
    p = tmp_path / "ok.json"
    p.write_text(json.dumps({"ok": True, "file": "f", "bytes": 1, "at": fresh.strftime("%Y-%m-%dT%H:%M:%SZ")}))
    monkeypatch.setattr(backup_status, "BACKUP_STATUS_PATH", p)
    assert SelfOpsService(user_id="u")._check_named(None, "check:nightly_backup_fresh", "nightly_backup_fresh") is None
