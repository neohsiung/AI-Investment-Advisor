import os
import json
import pytest
from src.services.evolution_metrics import EvolutionMetrics

def test_record_reflection_event(tmp_path):
    log_file = tmp_path / "test_evolution_metrics.jsonl"
    metrics = EvolutionMetrics(log_path=str(log_file))
    
    metrics.record_reflection_event(
        tool_name="get_market_data",
        error_type="RateLimitError",
        action="retry_with_fast_model",
        success=True,
        duration_ms=450
    )
    
    assert log_file.exists()
    with open(log_file, "r") as f:
        line = f.readline()
        data = json.loads(line)
        
    assert data["event_type"] == "self_healing_reflection"
    details = data["details"]
    assert details["tool_name"] == "get_market_data"
    assert details["error_type"] == "RateLimitError"
    assert details["action"] == "retry_with_fast_model"
    assert details["success"] is True
    assert details["duration_ms"] == 450
    assert "timestamp" in data

def test_generate_report_with_reflection(tmp_path):
    log_file = tmp_path / "test_report.jsonl"
    metrics = EvolutionMetrics(log_path=str(log_file))
    
    metrics.record_reflection_event("tool1", "err1", "act1", True)
    metrics.record_reflection_event("tool2", "err2", "act2", False)
    metrics.record_event("gap_detected", {"gap": "test"})
    
    report = metrics.generate_report()
    assert "self_healing_reflection: 2" in report
    assert "gap_detected: 1" in report
    assert "Total Evolution Events: 3" in report
