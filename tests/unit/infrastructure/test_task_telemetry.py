"""
Unit tests for task_runs telemetry (self-ops Loop 2).
task_runs 遙測單元測試。
"""
from unittest.mock import patch, MagicMock

from src.infrastructure import task_telemetry


def _capture_record():
    """Patch _record_run and return the mock."""
    return patch.object(task_telemetry, "_record_run")


class TestPostrunClassification:
    def test_success_recorded(self):
        task = MagicMock()
        task.name = "src.infrastructure.tasks.sentinel_tick"
        with _capture_record() as rec:
            task_telemetry._on_task_postrun(
                task_id="t1", task=task, retval="Success", state="SUCCESS"
            )
        rec.assert_called_once()
        args, kwargs = rec.call_args
        assert args[2] == "success"

    def test_error_string_return_is_soft_fail(self):
        """The legacy 'return "Error: ..."' convention must surface as soft_fail."""
        task = MagicMock()
        task.name = "src.infrastructure.tasks.distill_memories"
        with _capture_record() as rec:
            task_telemetry._on_task_postrun(
                task_id="t2", task=task,
                retval="Error: 'CognitiveMemoryManager' object has no attribute 'distill_memories'",
                state="SUCCESS",
            )
        args, kwargs = rec.call_args
        assert args[2] == "soft_fail"
        assert kwargs["error_class"] == "SoftFailReturn"
        assert "CognitiveMemoryManager" in kwargs["error_snippet"]

    def test_error_case_insensitive(self):
        task = MagicMock()
        task.name = "x"
        with _capture_record() as rec:
            task_telemetry._on_task_postrun(
                task_id="t3", task=task, retval="  error: boom", state="SUCCESS"
            )
        assert rec.call_args[0][2] == "soft_fail"

    def test_non_error_string_is_success(self):
        task = MagicMock()
        task.name = "x"
        with _capture_record() as rec:
            task_telemetry._on_task_postrun(
                task_id="t4", task=task,
                retval="OK: archived 3 memories (0 errors)", state="SUCCESS"
            )
        assert rec.call_args[0][2] == "success"

    def test_failure_state_not_double_recorded(self):
        """FAILURE state is handled by the failure signal, not postrun."""
        task = MagicMock()
        task.name = "x"
        with _capture_record() as rec:
            task_telemetry._on_task_postrun(
                task_id="t5", task=task, retval=None, state="FAILURE"
            )
        rec.assert_not_called()


class TestFailureSignal:
    def test_exception_recorded_with_class(self):
        sender = MagicMock()
        sender.name = "src.infrastructure.tasks.distill_memories"
        with _capture_record() as rec:
            task_telemetry._on_task_failure(
                task_id="t6", exception=AttributeError("no such method"), sender=sender
            )
        args, kwargs = rec.call_args
        assert args[2] == "failure"
        assert kwargs["error_class"] == "AttributeError"


class TestDuration:
    def test_duration_computed_from_prerun(self):
        task = MagicMock()
        task.name = "x"
        task_telemetry._on_task_prerun(task_id="t7", task=task)
        with _capture_record() as rec:
            task_telemetry._on_task_postrun(
                task_id="t7", task=task, retval="ok", state="SUCCESS"
            )
        assert rec.call_args[1]["duration_ms"] is not None
        assert rec.call_args[1]["duration_ms"] >= 0
        # start-time entry must be cleaned up
        assert "t7" not in task_telemetry._task_start_times


class TestWriteResilience:
    def test_record_run_swallows_db_errors(self):
        """Telemetry must never raise into the task path."""
        with patch("src.data.database.get_db_engine", side_effect=RuntimeError("db down")):
            task_telemetry._record_run("x", "t8", "success")  # must not raise
