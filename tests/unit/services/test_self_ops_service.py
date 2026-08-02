"""
Unit tests for SelfOpsService (dead-man switches + drift detection).
自我維運哨兵單元測試。
"""
from celery.schedules import crontab

from src.services.self_ops_service import derive_max_gap_seconds, _NAMED_CHECKS


class TestDeriveMaxGap:
    def test_every_minute(self):
        assert derive_max_gap_seconds(crontab(minute="*")) == 300

    def test_every_n_minutes(self):
        # */15 → 15*60*2 + 300 = 2100
        assert derive_max_gap_seconds(crontab(minute="*/15")) == 2100

    def test_every_5_minutes(self):
        assert derive_max_gap_seconds(crontab(minute="*/5")) == 900

    def test_hourly(self):
        # fixed minute, hour "*" → 2.5h
        assert derive_max_gap_seconds(crontab(minute=0)) == 2 * 3600 + 1800

    def test_daily(self):
        assert derive_max_gap_seconds(crontab(hour=2, minute=0)) == 26 * 3600

    def test_weekday_range(self):
        # Mon-Fri daily task: worst gap is the weekend (Fri→Mon)
        assert derive_max_gap_seconds(crontab(hour=17, minute=0, day_of_week="1-5")) == 74 * 3600

    def test_single_weekly_day(self):
        assert derive_max_gap_seconds(crontab(hour=8, minute=0, day_of_week="0")) == 8 * 86400

    def test_monthly(self):
        assert derive_max_gap_seconds(crontab(hour=9, minute=0, day_of_month="1")) == 32 * 86400


class TestNamedChecks:
    def test_risk_keywords_check_defined(self):
        spec = _NAMED_CHECKS["risk_keywords_nonempty"]
        assert spec["ok_when"](232) is True
        assert spec["ok_when"](0) is False
        assert spec["critical"] is True

    def test_decision_outcomes_check_defined(self):
        spec = _NAMED_CHECKS["decision_outcomes_not_stuck"]
        assert spec["ok_when"](0) is True
        assert spec["ok_when"](4) is False


class TestBeatScheduleCoverage:
    def test_all_beat_tasks_derivable(self):
        """Every live beat entry must produce a sane dead-man gap."""
        from src.infrastructure.celery_app import app
        for entry_name, entry in app.conf.beat_schedule.items():
            gap = derive_max_gap_seconds(entry["schedule"])
            assert 60 <= gap <= 40 * 86400, f"{entry_name}: unreasonable gap {gap}"

    def test_self_ops_check_is_scheduled(self):
        """The watcher itself must be on the schedule (who watches the watchmen)."""
        from src.infrastructure.celery_app import app
        tasks = [e["task"] for e in app.conf.beat_schedule.values()]
        assert "src.infrastructure.tasks.self_ops_check" in tasks

    def test_cost_anomaly_check_is_scheduled(self):
        from src.infrastructure.celery_app import app
        tasks = [e["task"] for e in app.conf.beat_schedule.values()]
        assert "src.infrastructure.tasks.cost_anomaly_check" in tasks


class TestCostAnomaly:
    def _svc_with_rows(self, last_24h, daily_rows):
        """Build a SelfOpsService with a stubbed engine returning fixed rows."""
        from unittest.mock import MagicMock, patch
        from src.services.self_ops_service import SelfOpsService
        svc = SelfOpsService(user_id="test-user")
        conn = MagicMock()
        results = [
            MagicMock(fetchone=MagicMock(return_value=(last_24h,))),
            MagicMock(fetchall=MagicMock(return_value=[(None, c) for c in daily_rows])),
        ]
        conn.execute.side_effect = results
        engine = MagicMock()
        engine.connect.return_value.__enter__ = MagicMock(return_value=conn)
        engine.connect.return_value.__exit__ = MagicMock(return_value=False)
        return svc, patch.object(svc, "_engine", return_value=engine)

    def test_projection_breach(self):
        from unittest.mock import patch as _p
        svc, engine_patch = self._svc_with_rows(last_24h=10.0, daily_rows=[])
        with engine_patch, _p.object(svc, "_emit_alerts") as emit:
            result = svc.check_cost_anomaly()
        assert result["projected_week_usd"] == 70.0
        assert any(b["name"] == "cost:weekly_projection" for b in result["breaches"])
        emit.assert_called_once()

    def test_no_breach_under_budget(self):
        from unittest.mock import patch as _p
        svc, engine_patch = self._svc_with_rows(last_24h=2.0, daily_rows=[2.0, 2.1, 1.9, 2.0, 2.05])
        with engine_patch, _p.object(svc, "_emit_alerts") as emit:
            result = svc.check_cost_anomaly()
        assert result["breaches"] == []
        emit.assert_not_called()

    def test_daily_spike_detected(self):
        from unittest.mock import patch as _p
        # 4 quiet days then a huge final day → spike (still under weekly budget projection)
        svc, engine_patch = self._svc_with_rows(last_24h=1.0, daily_rows=[1.0, 1.1, 0.9, 1.0, 4.0])
        with engine_patch, _p.object(svc, "_emit_alerts"):
            result = svc.check_cost_anomaly()
        assert any(b["name"] == "cost:daily_spike" for b in result["breaches"])

    def test_insufficient_history_skips_sigma(self):
        from unittest.mock import patch as _p
        # Only 3 days: sigma check must be skipped, no false positive
        svc, engine_patch = self._svc_with_rows(last_24h=1.0, daily_rows=[1.0, 1.0, 9.0])
        with engine_patch, _p.object(svc, "_emit_alerts"):
            result = svc.check_cost_anomaly()
        assert not any(b["name"] == "cost:daily_spike" for b in result["breaches"])


class TestTieredRemediation:
    """
    2026-07-14 (B-P2.3): T1 (auto re-enqueue, capped) -> T2 (advanced-tier
    diagnosis, never auto-applied) -> T3 (Telegram page).
    """

    def _svc_with_history(self, t1_count, t2_row):
        from unittest.mock import MagicMock, patch
        from src.services.self_ops_service import SelfOpsService
        svc = SelfOpsService(user_id="test-user")
        conn = MagicMock()
        conn.execute.return_value.fetchone.side_effect = [(t1_count,), t2_row]
        engine = MagicMock()
        engine.connect.return_value.__enter__ = MagicMock(return_value=conn)
        engine.connect.return_value.__exit__ = MagicMock(return_value=False)
        return svc, patch.object(svc, "_engine", return_value=engine)

    def test_dispatches_to_t1_when_under_attempt_cap(self):
        from unittest.mock import patch
        svc, engine_patch = self._svc_with_history(t1_count=0, t2_row=None)
        with engine_patch, patch.object(svc, "_remediate_t1", return_value="did t1") as mock_t1, \
             patch.object(svc, "_remediate_t2") as mock_t2, patch.object(svc, "_remediate_t3") as mock_t3:
            result = svc._remediate("taskA", "TIMEOUT", "boom")
        mock_t1.assert_called_once_with("taskA", "TIMEOUT")
        mock_t2.assert_not_called()
        mock_t3.assert_not_called()
        assert result == "did t1"

    def test_dispatches_to_t2_after_t1_cap_exhausted(self):
        from unittest.mock import patch
        svc, engine_patch = self._svc_with_history(t1_count=2, t2_row=None)
        with engine_patch, patch.object(svc, "_remediate_t1") as mock_t1, \
             patch.object(svc, "_remediate_t2", return_value="did t2") as mock_t2, patch.object(svc, "_remediate_t3") as mock_t3:
            result = svc._remediate("taskA", "TIMEOUT", "boom")
        mock_t1.assert_not_called()
        mock_t2.assert_called_once_with("taskA", "TIMEOUT", "boom")
        mock_t3.assert_not_called()
        assert result == "did t2"

    def test_dispatches_to_t3_after_t2_already_done(self):
        from unittest.mock import patch
        svc, engine_patch = self._svc_with_history(t1_count=2, t2_row=("root cause: X",))
        with engine_patch, patch.object(svc, "_remediate_t1") as mock_t1, \
             patch.object(svc, "_remediate_t2") as mock_t2, patch.object(svc, "_remediate_t3", return_value="did t3") as mock_t3:
            result = svc._remediate("taskA", "TIMEOUT", "boom")
        mock_t1.assert_not_called()
        mock_t2.assert_not_called()
        mock_t3.assert_called_once_with("taskA", "TIMEOUT", "root cause: X")
        assert result == "did t3"

    def test_lookup_failure_takes_no_action(self):
        from unittest.mock import patch
        from src.services.self_ops_service import SelfOpsService
        svc = SelfOpsService(user_id="test-user")
        with patch.object(svc, "_engine", side_effect=Exception("db down")), \
             patch.object(svc, "_remediate_t1") as mock_t1:
            result = svc._remediate("taskA", "TIMEOUT", "boom")
        mock_t1.assert_not_called()
        assert "no action" in result

    def test_t1_reenqueues_via_celery_send_task(self):
        from unittest.mock import MagicMock, patch
        from src.services.self_ops_service import SelfOpsService
        svc = SelfOpsService(user_id="test-user")
        mock_celery_app = MagicMock()
        with patch.object(svc, "_log_remediation") as mock_log, \
             patch("src.infrastructure.celery_app.app", mock_celery_app):
            action = svc._remediate_t1("taskA", "TIMEOUT")
        mock_celery_app.send_task.assert_called_once_with("taskA", args=("test-user",))
        mock_log.assert_called_once()
        assert mock_log.call_args[0][2] == "T1"
        assert "re-enqueued" in action

    def test_t1_handles_celery_failure_gracefully(self):
        from unittest.mock import MagicMock, patch
        from src.services.self_ops_service import SelfOpsService
        svc = SelfOpsService(user_id="test-user")
        mock_celery_app = MagicMock()
        mock_celery_app.send_task.side_effect = Exception("broker down")
        with patch.object(svc, "_log_remediation"), \
             patch("src.infrastructure.celery_app.app", mock_celery_app):
            action = svc._remediate_t1("taskA", "TIMEOUT")
        assert "re-enqueue failed" in action

    def test_t2_logs_diagnosis_and_never_auto_applies(self):
        from unittest.mock import patch
        from src.services.self_ops_service import SelfOpsService
        svc = SelfOpsService(user_id="test-user")
        with patch.object(svc, "_run_diagnosis", return_value="likely a stale token"), \
             patch.object(svc, "_log_remediation") as mock_log:
            action = svc._remediate_t2("taskA", "AUTH_FAILURE", "401 error")
        assert "not auto-applied" in action
        assert "likely a stale token" in action
        mock_log.assert_called_once_with("taskA", "AUTH_FAILURE", "T2", "diagnosed (not auto-applied)", diagnosis="likely a stale token")

    def test_t3_pages_with_prior_diagnosis_attached(self):
        from unittest.mock import AsyncMock, MagicMock, patch
        from src.services.self_ops_service import SelfOpsService
        svc = SelfOpsService(user_id="test-user")
        mock_notif = MagicMock()
        mock_notif.notify_all = AsyncMock(return_value=None)
        with patch.object(svc, "_log_remediation") as mock_log, \
             patch("src.services.settings_service.SettingsService"), \
             patch("src.services.notification_service.NotificationService.create_with_settings", return_value=mock_notif):
            action = svc._remediate_t3("taskA", "AUTH_FAILURE", "likely a stale token")
        mock_log.assert_called_once_with("taskA", "AUTH_FAILURE", "T3", "paged human via notification", diagnosis="likely a stale token")
        mock_notif.notify_all.assert_called_once()
        assert mock_notif.notify_all.call_args.kwargs["content"].count("likely a stale token") == 1
        assert action == "paged human via notification"

    def test_check_repeat_failures_groups_by_error_class(self):
        from unittest.mock import MagicMock, patch
        from src.services.self_ops_service import SelfOpsService
        svc = SelfOpsService(user_id="test-user")
        conn = MagicMock()
        conn.execute.return_value.fetchall.return_value = [("taskA", "TIMEOUT", 3, "timed out")]

        with patch.object(svc, "_remediate", return_value="did something") as mock_remediate:
            breaches = svc._check_repeat_failures(conn)

        mock_remediate.assert_called_once_with("taskA", "TIMEOUT", "timed out")
        assert len(breaches) == 1
        assert breaches[0]["name"] == "repeat:taskA:TIMEOUT"
        assert "did something" in breaches[0]["detail"]
