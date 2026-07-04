import pytest
from unittest.mock import MagicMock, patch
from src.services.scheduler_service import SchedulerService


@pytest.fixture
def mock_scheduler_deps():
    with patch('src.services.scheduler_service.SystemEngineerAgent') as eng_mock, \
         patch('src.data.database.get_db_engine') as db_mock, \
         patch('src.services.scheduler_service.subprocess.run') as sub_mock, \
         patch('src.services.scheduler_service.schedule') as schedule_mock, \
         patch('src.services.backtest_service.BacktestService') as backtest_mock, \
         patch('src.repositories.settings_repository.AlchemySettingsRepository') as settings_mock:
        yield {
            "engineer": eng_mock,
            "db": db_mock,
            "subprocess": sub_mock,
            "schedule": schedule_mock,
            "backtest": backtest_mock,
            "settings": settings_mock
        }

# test_get_all_users removed - v5.0 moves to strict single-user context
    
def test_job_daily_check_runs(mock_scheduler_deps):
    service = SchedulerService(user_id="test_user")
    
    # Mock time to be a weekday (Monday=0)
    with patch('src.services.scheduler_service.get_current_time') as time_mock:
        time_mock.return_value.weekday.return_value = 0 # Monday
        
        # v5.0: runs for self.user_id directly
        service.job_daily_check()
    
    # Should call subprocess for workflow daily
    mock_scheduler_deps['subprocess'].assert_called()
    args, _ = mock_scheduler_deps['subprocess'].call_args
    assert "daily" in args[0]
    # Check that user_id "test_user" is passed to subprocess
    assert "test_user" in args[0]

def test_job_daily_check_no_users(mock_scheduler_deps):
    service = SchedulerService(user_id="test_user")
    with patch('src.services.scheduler_service.get_current_time') as time_mock:
        time_mock.return_value.weekday.return_value = 0
        # In v5.0, job_daily_check always runs for self.user_id
        service.job_daily_check()
        mock_scheduler_deps['subprocess'].assert_called()

def test_job_daily_check_skips_saturday(mock_scheduler_deps):
    service = SchedulerService(user_id="test_user")
    
    with patch('src.services.scheduler_service.get_current_time') as time_mock:
        time_mock.return_value.weekday.return_value = 5 # Saturday
        
        service.job_daily_check()
        
        mock_scheduler_deps['subprocess'].assert_not_called()

def test_job_daily_check_exception(mock_scheduler_deps):
    service = SchedulerService(user_id="test_user")
    with patch('src.services.scheduler_service.get_current_time') as time_mock:
        time_mock.return_value.weekday.return_value = 0
        # Simulate subprocess error
        mock_scheduler_deps['subprocess'].side_effect = Exception("Boom")
        service.job_daily_check()
        # Should not crash, but log error
        assert mock_scheduler_deps['subprocess'].call_count == 1

def test_reload_schedule(mock_scheduler_deps):
    service = SchedulerService(user_id="test_user")
    
    # Mock the scheduler instance to track calls
    service.scheduler = MagicMock()
    
    mock_scheduler_deps['engineer'].return_value.get_schedule_config.return_value = {
        "schedule_daily": "10:00",
        "schedule_weekly": "11:00",
        "schedule_daily_days": "monday,tuesday"
    }
    
    # Mock the time conversion helper to return the time as-is
    # Mock the time conversion helper to return the time as-is with 0 day offset
    with patch('src.services.scheduler_service.convert_user_time_to_system_time', side_effect=lambda x: (x, 0)):
        service.reload_schedule()
        
        # Check scheduler instance calls
        service.scheduler.clear.assert_called()
        # Should be called for monday and tuesday
        service.scheduler.every.return_value.monday.at.assert_any_call("10:00")
        service.scheduler.every.return_value.tuesday.at.assert_any_call("10:00")
        
        # Weekly
        service.scheduler.every.return_value.saturday.at.assert_any_call("11:00")

def test_check_reload_signal_true(mock_scheduler_deps):
    service = SchedulerService(user_id="test_user")
    
    # Mock Settings Repo return
    mock_repo = mock_scheduler_deps['settings'].return_value
    mock_repo.get.return_value = 'true'
    
    with patch.object(service, 'reload_schedule') as reload_mock:
        service._check_reload_signal()
        
        reload_mock.assert_called()
        # Verify update to false
        mock_repo.set.assert_called_with('test_user', 'scheduler_reload_signal', False)

    
def test_check_reload_signal_false(mock_scheduler_deps):
    service = SchedulerService(user_id="test_user")
    
    # Mock Settings Repo return false
    mock_repo = mock_scheduler_deps['settings'].return_value
    mock_repo.get.return_value = 'false'
    
    with patch.object(service, 'reload_schedule') as reload_mock:
        service._check_reload_signal()
        reload_mock.assert_not_called()

def test_job_weekly_report(mock_scheduler_deps):
    service = SchedulerService(user_id="test_user")
    service.job_weekly_report()
    mock_scheduler_deps['subprocess'].assert_called()
    args, _ = mock_scheduler_deps['subprocess'].call_args
    assert "weekly" in args[0]
    assert "test_user" in args[0]

def test_job_weekly_report_exception(mock_scheduler_deps):
    service = SchedulerService(user_id="test_user")
    mock_scheduler_deps['subprocess'].side_effect = Exception("Fail")
    service.job_weekly_report()
    assert mock_scheduler_deps['subprocess'].call_count == 1

def test_job_weekly_validation(mock_scheduler_deps):
    from unittest.mock import AsyncMock
    service = SchedulerService(user_id="test_user")
    
    mock_bt_cls = mock_scheduler_deps['backtest']
    mock_bt_instance = mock_bt_cls.return_value
    mock_bt_instance.run_simulation = AsyncMock()
    
    service.job_weekly_validation()
    
    # Should call run_simulation for default tickers
    assert mock_bt_instance.run_simulation.call_count >= 1
    # Check args for one of them
    call_args_list = mock_bt_instance.run_simulation.call_args_list
    tickers_called = [args[0] for args, kwargs in call_args_list]
    assert "AAPL" in tickers_called
    assert "SPY" in tickers_called

def test_job_monthly_refinement(mock_scheduler_deps):
    service = SchedulerService(user_id="test_user")
    # Mock execution
    service.job_monthly_refinement()
    
    # Verify subprocess call to refinement.py
    mock_scheduler_deps['subprocess'].assert_called()
    args, _ = mock_scheduler_deps['subprocess'].call_args
    assert "refinement.py" in str(args[0])

def test_check_monthly_job_triggers(mock_scheduler_deps):
    service = SchedulerService(user_id="test_user")
    with patch('src.services.scheduler_service.get_current_time') as time_mock:
        time_mock.return_value.day = 1 # 1st day matches
        
        with patch.object(service, 'job_monthly_refinement') as job_mock:
            service.check_monthly_job()
            job_mock.assert_called()

def test_check_monthly_job_skips(mock_scheduler_deps):
    service = SchedulerService(user_id="test_user")
    with patch('src.services.scheduler_service.get_current_time') as time_mock:
        time_mock.return_value.day = 2 # Not 1st
        
        with patch.object(service, 'job_monthly_refinement') as job_mock:
            service.check_monthly_job()
            job_mock.assert_not_called()
