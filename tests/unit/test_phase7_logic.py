import pytest
import os
import json
from unittest.mock import MagicMock, patch
from src.prompts.reflection_prompt import ReflectionPrompt
from src.services.budget_aware_model_router import BudgetAwareModelRouter
from src.services.evolution_metrics import EvolutionMetrics

def test_reflection_prompt_compressed_efficiency():
    """驗證壓縮版 Prompt 確實比標準版短 (Phase 7.3.3)"""
    tool = "search_stocks"
    args = {"query": "AAPL"}
    error = "Rate limit exceeded"
    
    standard = ReflectionPrompt.build(tool, args, error)
    compressed = ReflectionPrompt.build_compressed(tool, args, error)
    
    assert len(compressed) < len(standard)
    assert "JSON" in compressed
    assert tool in compressed

def test_budget_aware_router_critical_logic():
    """驗證預算緊急判定邏輯 (Phase 7.3.3)"""
    mock_settings = MagicMock()
    mock_token_logger = MagicMock()
    
    router = BudgetAwareModelRouter(mock_settings, mock_token_logger)
    
    # CASE 1: Below soft limit ($10.0 < $16.0)
    mock_token_logger.get_user_spending.return_value = {"total_cost": 10.0}
    assert router.is_budget_critical("user_1") is False
    
    # CASE 2: Above soft limit ($17.0 > $16.0)
    mock_token_logger.get_user_spending.return_value = {"total_cost": 17.0}
    assert router.is_budget_critical("user_1") is True

def test_evolution_metrics_logging(tmp_path):
    """驗證 EvolutionMetrics 能正確寫入 JSONL (Phase 7.1.2)"""
    metrics_file = tmp_path / "evolution_metrics.jsonl"
    
    # Pass the log_path directly to constructor
    metrics = EvolutionMetrics(log_path=str(metrics_file))
    metrics.record_reflection_event(
        tool_name="test_tool",
        error_type="ValueError",
        action="retry",
        success=True,
        duration_ms=500
    )
    
    assert metrics_file.exists()
    with open(metrics_file, "r") as f:
        line = f.readline()
        data = json.loads(line)
        # record_reflection_event calls record_event with 'self_healing_reflection' type
        assert data["event_type"] == "self_healing_reflection"
        assert data["details"]["tool_name"] == "test_tool"
        assert data["details"]["success"] is True
        assert "timestamp" in data
