"""
Tests for EvolutionMetrics to improve coverage.
"""
import json
import os
import tempfile
import pytest
from unittest.mock import patch, MagicMock
from src.services.evolution_metrics import EvolutionMetrics


class TestEvolutionMetrics:
    """Test EvolutionMetrics record and report functionality."""

    def setup_method(self):
        """Use a temp directory for log files."""
        self.tmpdir = tempfile.mkdtemp()
        self.log_path = os.path.join(self.tmpdir, "logs", "evolution_metrics.jsonl")
        self.metrics = EvolutionMetrics(log_path=self.log_path)

    def test_init_creates_log_directory(self):
        """Initializing EvolutionMetrics creates the log directory."""
        assert os.path.isdir(os.path.dirname(self.log_path))

    def test_record_event_basic(self):
        """record_event writes a JSON line to the log file."""
        self.metrics.record_event("gap_detected", {"skill": "momentum"})
        assert os.path.exists(self.log_path)
        with open(self.log_path, "r") as f:
            line = f.readline()
        record = json.loads(line)
        assert record["event_type"] == "gap_detected"
        assert record["details"]["skill"] == "momentum"
        assert "timestamp" in record

    def test_record_event_no_details(self):
        """record_event with no details uses empty dict."""
        self.metrics.record_event("scaffolding_started")
        with open(self.log_path, "r") as f:
            line = f.readline()
        record = json.loads(line)
        assert record["event_type"] == "scaffolding_started"
        assert record["details"] == {}

    def test_record_multiple_events(self):
        """Multiple events are appended to the log file."""
        self.metrics.record_event("gap_detected")
        self.metrics.record_event("scaffolding_success")
        self.metrics.record_event("skill_hot_reloaded")
        with open(self.log_path, "r") as f:
            lines = f.readlines()
        assert len(lines) == 3
        types = [json.loads(l)["event_type"] for l in lines]
        assert "gap_detected" in types
        assert "scaffolding_success" in types
        assert "skill_hot_reloaded" in types

    def test_record_event_handles_write_error(self):
        """record_event logs error but does not raise on write failure."""
        self.metrics.log_path = "/nonexistent/path/that/cannot/be/created/metrics.jsonl"
        # Should not raise
        self.metrics.record_event("test_event")

    def test_record_reflection_event(self):
        """record_reflection_event writes self_healing_reflection event."""
        self.metrics.record_reflection_event(
            tool_name="search_tool",
            error_type="timeout",
            action="retry",
            success=True,
            duration_ms=150,
        )
        with open(self.log_path, "r") as f:
            line = f.readline()
        record = json.loads(line)
        assert record["event_type"] == "self_healing_reflection"
        assert record["details"]["tool_name"] == "search_tool"
        assert record["details"]["error_type"] == "timeout"
        assert record["details"]["action"] == "retry"
        assert record["details"]["success"] is True
        assert record["details"]["duration_ms"] == 150

    def test_record_reflection_event_failure(self):
        """record_reflection_event with success=False."""
        self.metrics.record_reflection_event(
            tool_name="data_tool",
            error_type="connection_error",
            action="fallback",
            success=False,
        )
        with open(self.log_path, "r") as f:
            line = f.readline()
        record = json.loads(line)
        assert record["details"]["success"] is False
        assert record["details"]["duration_ms"] == 0

    def test_generate_report_no_file(self):
        """generate_report returns message when no log file exists."""
        report = self.metrics.generate_report()
        assert "No evolution data available" in report

    def test_generate_report_with_events(self):
        """generate_report summarizes events correctly."""
        self.metrics.record_event("gap_detected")
        self.metrics.record_event("gap_detected")
        self.metrics.record_event("scaffolding_success")
        self.metrics.record_event("skill_hot_reloaded")

        report = self.metrics.generate_report()
        assert "Total Evolution Events: 4" in report
        assert "gap_detected: 2" in report
        assert "scaffolding_success: 1" in report
        assert "skill_hot_reloaded: 1" in report

    def test_generate_report_skips_empty_lines(self):
        """generate_report skips blank lines in log file."""
        with open(self.log_path, "w") as f:
            f.write("\n")
            f.write(json.dumps({"event_type": "test_event", "details": {}}) + "\n")
            f.write("\n")
        report = self.metrics.generate_report()
        assert "Total Evolution Events: 1" in report

    def test_generate_report_skips_invalid_json(self):
        """generate_report skips lines with invalid JSON."""
        with open(self.log_path, "w") as f:
            f.write("not-valid-json\n")
            f.write(json.dumps({"event_type": "valid_event", "details": {}}) + "\n")
        report = self.metrics.generate_report()
        assert "Total Evolution Events: 1" in report

    def test_generate_report_handles_read_error(self):
        """generate_report handles file read errors gracefully."""
        # Create the file first
        self.metrics.record_event("test")
        # Now patch open to raise
        with patch("builtins.open", side_effect=IOError("read error")):
            report = self.metrics.generate_report()
        assert "Error" in report

    def test_generate_report_header(self):
        """generate_report includes the header."""
        self.metrics.record_event("gap_detected")
        report = self.metrics.generate_report()
        assert "Phase 5C" in report or "Evolution Metrics" in report
