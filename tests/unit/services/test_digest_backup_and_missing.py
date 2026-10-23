"""Weekly charter digest: nightly-backup line and readable missing-criteria lines.
章程週報：夜間備份一行，以及可讀的「未滿足條件」。"""
import json
from datetime import datetime, timedelta, timezone

from src.services.charter_digest_service import _backup_status, _readable_missing

NOW = datetime(2026, 10, 24, 14, 35, tzinfo=timezone.utc)


def _write(tmp_path, **kw):
    p = tmp_path / "s.json"
    p.write_text(json.dumps(kw), encoding="utf-8")
    return p


def test_fresh_successful_backup_is_reported_with_size_and_age(tmp_path):
    at = (NOW - timedelta(hours=11)).isoformat().replace("+00:00", "Z")
    r = _backup_status(NOW, _write(tmp_path, ok=True, file="db_backup_x.sql", bytes=321_000_000, at=at, reason=""))
    assert r["ok"] is True and r["mb"] == 321.0 and r["stale"] is False and r["age_days"] < 1


def test_backup_older_than_two_days_is_flagged_stale(tmp_path):
    at = (NOW - timedelta(days=3)).isoformat().replace("+00:00", "Z")
    assert _backup_status(NOW, _write(tmp_path, ok=True, file="f", bytes=1, at=at, reason=""))["stale"] is True


def test_failed_backup_keeps_its_reason(tmp_path):
    at = NOW.isoformat().replace("+00:00", "Z")
    r = _backup_status(NOW, _write(tmp_path, ok=False, file="", bytes=0, at=at, reason="docker not found"))
    assert r["ok"] is False and r["reason"] == "docker not found"


def test_missing_status_file_is_an_error_never_fine(tmp_path):
    assert "error" in _backup_status(NOW, tmp_path / "nope.json")


def test_readable_missing_dry_run_and_drill_in_plain_chinese():
    a = _readable_missing({"criterion": "dry_run_90d", "status": "not_ok",
                           "value": {"days": 3, "required_days": 90, "keys_without_verdict": ["a"]}})
    assert "未滿足" in a and "已 3 天／需 90 天" in a and "尚無判決的參數：a" in a
    b = _readable_missing({"criterion": "drill", "status": "not_ok", "value": {"drills": 0, "passed": 0}})
    assert "停機演練通過" in b and "POST /charter/drill" in b


def test_readable_missing_marks_not_measurable():
    m = _readable_missing({"criterion": "no_freeze_30d", "status": "not_measurable", "value": {"error": "x"}})
    assert m.startswith("- 無法量測")


def test_council_counts_and_unreadable_are_reported():
    """The digest shows councils run and skipped by the halt gate; a failed read is 'unknown', never zero.
    週報顯示議會場數與停機略過次數；讀不到是未知，不是 0。"""
    from sqlalchemy import create_engine, text
    from datetime import datetime, timedelta, timezone
    from src.services import charter_digest_service as cds
    from src.services.council_halt_gate import SKIP_MARKER
    now = datetime(2026, 10, 24, 12, 0, tzinfo=timezone.utc)
    eng = create_engine("sqlite:///:memory:")
    with eng.begin() as c:
        c.execute(text("CREATE TABLE event_logs (title TEXT, created_at TIMESTAMP)"))
        c.execute(text("CREATE TABLE council_minutes (created_at TIMESTAMP)"))
        for d in (1, 2, 3, 20):
            c.execute(text("INSERT INTO event_logs VALUES (:t, :s)"), {"t": SKIP_MARKER, "s": now - timedelta(days=d)})
        c.execute(text("INSERT INTO event_logs VALUES ('other', :s)"), {"s": now - timedelta(days=1)})
        for d in (1, 2, 30):
            c.execute(text("INSERT INTO council_minutes VALUES (:s)"), {"s": now - timedelta(days=d)})
    assert cds._council_skipped(eng, now) == {"skipped": 3, "ran": 2}      # the 20-day-old and 30-day-old rows are outside
    bad = cds._council_skipped(create_engine("sqlite:///:memory:"), now)
    assert "error" in bad
