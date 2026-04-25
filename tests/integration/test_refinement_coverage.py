import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from src.services.refinement_service import RefinementService

@pytest.fixture
def anyio_backend():
    return 'asyncio'

class TestRefinementService:
    
    @pytest.mark.anyio
    @patch('src.services.refinement_service.setup_logger')
    @patch('src.services.refinement_service.PerformanceService')
    @patch('src.services.refinement_service.SystemEngineerAgent')
    @patch('src.services.refinement_service.NotificationService')
    async def test_run_monthly_refinement(self, MockNotification, MockEngineer, MockPerf, mock_logger):
        """Test running the monthly refinement process."""
        # Setup mocks
        mock_noti_instance = MagicMock()
        mock_noti_instance.send_report = AsyncMock(return_value=True)
        MockNotification.create_with_settings.return_value = mock_noti_instance
        
        mock_perf_instance = MockPerf.return_value
        mock_perf_instance.get_agent_performance.return_value = {
            "Momentum": {"win_rate": 0.8, "count": 10},
            "Fundamental": {"win_rate": 0.3, "count": 10}
        }
        
        mock_eng_instance = MockEngineer.return_value
        mock_eng_instance.run = AsyncMock(return_value=[
            {"target_agent": "Fundamental", "reason": "Low win rate"}
        ])
        
        # We need to mock SettingsService because it's imported inside __init__
        with patch('src.services.settings_service.SettingsService'):
            service = RefinementService(user_id="test@user.com")
            result = await service.run_monthly_refinement()
        
        assert result is True
        mock_noti_instance.send_report.assert_called()
    
    def test_merge_stats(self):
        """Test merging and normalizing statistics."""
        service = RefinementService(user_id="test@user.com", notification_service=MagicMock())
        stats = {
            "momentum": {"win_rate": 0.5, "count": 4},
            "UnknownAgent": {"win_rate": 1.0, "count": 1}
        }
        target_agents = ["Momentum", "Fundamental"]
        
        merged = service._merge_stats(stats, target_agents)
        
        assert "Momentum" in merged
        assert merged["Momentum"]["count"] == 4
        assert "Unknownagent" in merged or "UnknownAgent" in merged

    def test_generate_report(self):
        """Test generating report content."""
        service = RefinementService(user_id="test@user.com", notification_service=MagicMock())
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
