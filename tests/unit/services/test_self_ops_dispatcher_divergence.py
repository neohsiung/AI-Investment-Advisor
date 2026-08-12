"""
Regression tests for the dispatcher/child divergence dead-man switch.
派工／子任務落差 dead-man 監控的回歸測試。

Context (2026-08-10): the API leaked Redis connections until the server hit
`max number of clients reached`, and both Celery workers stopped consuming the
queue. The outage lasted three days and tripped no alert.

The reason is structural. `SelfOpsService` derives its expectations from the
Celery beat schedule, and the beat schedule only names *dispatchers*. A
dispatcher calls `.delay()`, which returns as soon as the broker accepts the
message, so it recorded `success` on every run while no worker ever executed
the child. Production `task_runs` over the final two days:

    dispatch_sentinel_tick   success   95   2026-08-10 14:30
    sentinel_tick            success    2   2026-08-09 22:15

Every monitored signal was green while the trading loop was dead.

2026-08-10：Redis 連線耗盡導致兩個 worker 停止消費佇列，事故持續三天且未觸發
任何告警——因為監控期望值衍生自 beat 排程，而排程只列出 dispatcher，而 .delay()
送出即返回，所以 dispatcher 一路回報成功。
"""
import inspect
import re

import pytest

from src.services.self_ops_service import (
    DISPATCHER_CHILD_TASKS,
    DIVERGENCE_MIN_DISPATCHES,
    DIVERGENCE_WINDOW_MINUTES,
    SelfOpsService,
    _TASK_PREFIX,
)


class TestDispatcherMapStaysInSyncWithCode:
    """
    The map is hand-maintained because the names are not derivable:
    `dispatch_broker_sync` fans out to `sync_broker_positions`. These tests
    read the dispatchers' actual source so drift fails CI instead of silently
    dropping a task out of monitoring.
    對照表為人工維護（名稱無法由慣例推導），故以原始碼比對防止漂移。
    """

    @staticmethod
    def _dispatchers_in_source():
        """Every `dispatch_*` task and the task its `.delay()` targets."""
        import src.infrastructure.tasks as tasks_mod

        found = {}
        for name in dir(tasks_mod):
            if not name.startswith("dispatch_"):
                continue
            fn = getattr(tasks_mod, name)
            try:
                src = inspect.getsource(fn)
            except (OSError, TypeError):
                continue
            targets = re.findall(r"(\w+)\.delay\(", src)
            if targets:
                found[name] = targets[0]
        return found

    def test_every_dispatcher_in_code_is_monitored(self):
        actual = self._dispatchers_in_source()
        missing = set(actual) - set(DISPATCHER_CHILD_TASKS)
        assert not missing, (
            f"dispatchers absent from DISPATCHER_CHILD_TASKS (they would fan out "
            f"unmonitored): {sorted(missing)}"
        )

    def test_no_stale_entries_in_the_map(self):
        actual = self._dispatchers_in_source()
        stale = set(DISPATCHER_CHILD_TASKS) - set(actual)
        assert not stale, (
            f"DISPATCHER_CHILD_TASKS names dispatchers that no longer exist: {sorted(stale)}"
        )

    def test_child_task_names_match_the_delay_call(self):
        actual = self._dispatchers_in_source()
        wrong = {
            d: (DISPATCHER_CHILD_TASKS[d], child)
            for d, child in actual.items()
            if d in DISPATCHER_CHILD_TASKS and DISPATCHER_CHILD_TASKS[d] != child
        }
        assert not wrong, f"mapped child != actual .delay() target: {wrong}"


class _FakeConn:
    """Returns canned (task_name, count) rows for the divergence query."""

    def __init__(self, counts):
        self._counts = counts

    def execute(self, *_args, **_kwargs):
        rows = [(f"{_TASK_PREFIX}{name}", n) for name, n in self._counts.items()]
        return _FakeResult(rows)


class _FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def fetchall(self):
        return self._rows


class TestDivergenceDetection:

    def test_flags_the_outage_signature(self):
        """
        The exact production shape: dispatcher busy, child silent.
        重現 production 的訊號形狀：dispatcher 忙碌、子任務靜默。
        """
        svc = SelfOpsService.__new__(SelfOpsService)
        conn = _FakeConn({"dispatch_sentinel_tick": 95, "sentinel_tick": 0})

        breaches = svc._check_dispatcher_divergence(conn)

        assert len(breaches) == 1
        assert breaches[0]["name"] == "divergence:dispatch_sentinel_tick"
        assert breaches[0]["severity"] == "critical"
        assert "sentinel_tick never ran" in breaches[0]["detail"]

    def test_healthy_fan_out_is_silent(self):
        svc = SelfOpsService.__new__(SelfOpsService)
        conn = _FakeConn({"dispatch_sentinel_tick": 60, "sentinel_tick": 60})

        assert svc._check_dispatcher_divergence(conn) == []

    def test_idle_low_frequency_dispatcher_is_not_a_breach(self):
        """
        A daily/weekly dispatcher that has not run enough times in the window
        must not read as broken just because its child is also idle.
        低頻 dispatcher 在窗口內次數不足時，不得因子任務同樣閒置而被誤判。
        """
        svc = SelfOpsService.__new__(SelfOpsService)
        conn = _FakeConn({
            "dispatch_daily_report": DIVERGENCE_MIN_DISPATCHES - 1,
            "generate_daily_report": 0,
        })

        assert svc._check_dispatcher_divergence(conn) == []

    def test_threshold_boundary_is_inclusive(self):
        svc = SelfOpsService.__new__(SelfOpsService)
        conn = _FakeConn({
            "dispatch_daily_report": DIVERGENCE_MIN_DISPATCHES,
            "generate_daily_report": 0,
        })

        assert len(svc._check_dispatcher_divergence(conn)) == 1

    def test_detail_names_the_window(self):
        svc = SelfOpsService.__new__(SelfOpsService)
        conn = _FakeConn({"dispatch_broker_sync": 12, "sync_broker_positions": 0})

        detail = svc._check_dispatcher_divergence(conn)[0]["detail"]

        assert str(DIVERGENCE_WINDOW_MINUTES) in detail
        assert "sync_broker_positions" in detail
