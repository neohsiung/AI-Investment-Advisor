"""
Tests for Refinement Service.
測試 Refinement 服務。
"""
import pytest
from unittest.mock import MagicMock, patch
from src.services.refinement_service import RefinementService

class TestRefinementService:
    
    @patch('src.services.refinement_service.setup_logger')
    @patch('src.services.refinement_service.PerformanceService')
    @patch('src.services.refinement_service.SystemEngineerAgent')
    @patch('src.services.refinement_service.EmailNotifier')
    def test_run_monthly_refinement(self, mock_notifier, mock_engineer, mock_perf, mock_logger):
        """Test running the monthly refinement process."""
        service = RefinementService(user_id="test@user.com")
        
        # Mock dependencies
        mock_perf.return_value.get_agent_performance.return_value = {
            "Momentum": {"win_rate": 0.8, "count": 10},
            "Fundamental": {"win_rate": 0.3, "count": 10}
        }
        mock_engineer.return_value.run.return_value = [
            {"target_agent": "Fundamental", "reason": "Low win rate"}
        ]
        
        result = service.run_monthly_refinement()
        
        assert result is True
        mock_notifier.return_value.send_report.assert_called()
    
    def test_merge_stats(self):
        """Test merging and normalizing statistics."""
        service = RefinementService()
        stats = {
            "momentum": {"win_rate": 0.5, "count": 4},
            "UnknownAgent": {"win_rate": 1.0, "count": 1}
        }
        target_agents = ["Momentum", "Fundamental"]
        
        merged = service._merge_stats(stats, target_agents)
        
        assert "Momentum" in merged
        assert merged["Momentum"]["count"] == 4
        assert "Unknownagent" in merged or "UnknownAgent" in merged # Depending on title()

    def test_generate_report(self):
        """Test generating report content."""
        service = RefinementService()
        merged_stats = {
            "Momentum": {"wins": 4.0, "count": 5},
            "Fundamental": {"wins": 1.0, "count": 5}
        }
        optimizations = [
            {"target_agent": "Fundamental", "reason": "Optimization needed"}
        ]
        target_agents = ["Momentum", "Fundamental"]
        
        report = service._generate_report(merged_stats, optimizations, target_agents)
        
        assert "Momentum" in report
        assert "Fundamental" in report
        assert "🟢 優異" in report
        assert "🔴 待優化" in report
        assert "APO Cycle" in report
