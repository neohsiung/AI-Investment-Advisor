import pytest
import uuid
from unittest.mock import MagicMock, patch
from src.services.experience_replay_service import ExperienceReplayService

class TestExperienceReplayService:
    @pytest.fixture
    def mock_repos(self):
        mock_sentinel_repo = MagicMock()
        mock_trans_repo = MagicMock()
        return mock_sentinel_repo, mock_trans_repo

    @pytest.fixture
    def service(self, mock_repos):
        sentinel_repo, trans_repo = mock_repos
        return ExperienceReplayService(sentinel_repo=sentinel_repo, trans_repo=trans_repo)

    def test_optimize_vix_thresholds_no_noise(self, service, mock_repos):
        sentinel_repo, _ = mock_repos
        user_id = "test_user"
        
        # Mock no alerts
        with patch('src.services.experience_replay_service.get_db_connection') as mock_db:
            mock_conn = MagicMock()
            mock_db.return_value.__enter__.return_value = mock_conn
            mock_conn.execute.return_value.scalar.return_value = 0
            
            result = service._optimize_vix_thresholds(user_id)
            assert result is None
            sentinel_repo.update_threshold.assert_not_called()

    def test_optimize_vix_thresholds_with_noise(self, service, mock_repos):
        sentinel_repo, _ = mock_repos
        user_id = "test_user"
        
        # Mock high alert density (e.g. 15 alerts)
        with patch('src.services.experience_replay_service.get_db_connection') as mock_db:
            mock_conn = MagicMock()
            mock_db.return_value.__enter__.return_value = mock_conn
            mock_conn.execute.return_value.scalar.return_value = 15
            
            sentinel_repo.get_all_thresholds.return_value = {"vix_high": 20.0}
            
            result = service._optimize_vix_thresholds(user_id)
            
            assert result is not None
            assert result["new"] == 21.0 # 20.0 * 1.05
            sentinel_repo.update_threshold.assert_called_with(
                "vix_high", 21.0, "ExperienceReplay", "Reduced noise: 15 alerts in 7d detected."
            )
