import pytest
from unittest.mock import MagicMock, patch
from src.services.scheduler_service import SchedulerService

@pytest.fixture
def mock_scheduler_deps():
    with patch('src.services.scheduler_service.SystemEngineerAgent') as eng_mock, \
         patch('src.services.scheduler_service.get_db_connection') as db_mock, \
         patch('src.services.scheduler_service.subprocess.run') as sub_mock, \
         patch('src.services.scheduler_service.schedule') as schedule_mock:
        yield {
            "engineer": eng_mock,
            "db": db_mock,
            "subprocess": sub_mock,
            "schedule": schedule_mock
        }

def test_job_daily_check_runs(mock_scheduler_deps):
    service = SchedulerService()
    
    # Mock time to be a weekday (Monday=0)
    with patch('src.services.scheduler_service.get_current_time') as time_mock:
        time_mock.return_value.weekday.return_value = 0 # Monday
        
        # Mock users
        with patch.object(service, 'get_all_users', return_value=['user@test.com']):
            service.job_daily_check()
            
            # Should call subprocess for workflow daily
            mock_scheduler_deps['subprocess'].assert_called()
            args, _ = mock_scheduler_deps['subprocess'].call_args
            assert "daily" in args[0]
            assert "user@test.com" in args[0]

def test_job_daily_check_skips_saturday(mock_scheduler_deps):
    service = SchedulerService()
    
    with patch('src.services.scheduler_service.get_current_time') as time_mock:
        time_mock.return_value.weekday.return_value = 5 # Saturday
        
        service.job_daily_check()
        
        mock_scheduler_deps['subprocess'].assert_not_called()

def test_reload_schedule(mock_scheduler_deps):
    service = SchedulerService()
    mock_scheduler_deps['engineer'].return_value.get_schedule_config.return_value = {
        "schedule_daily": "10:00",
        "schedule_weekly": "11:00"
    }
    
    service.reload_schedule()
    
    # Check schedule calls
    mock_scheduler_deps['schedule'].clear.assert_called()
    mock_scheduler_deps['schedule'].every.return_value.day.at.assert_any_call("10:00")
    mock_scheduler_deps['schedule'].every.return_value.saturday.at.assert_any_call("11:00")

def test_check_reload_signal_true(mock_scheduler_deps):
    service = SchedulerService()
    
    # Mock DB return
    mock_conn = mock_scheduler_deps['db'].return_value
    mock_conn.execute.return_value.fetchone.return_value = ['true']
    
    with patch.object(service, 'reload_schedule') as reload_mock:
        service._check_reload_signal()
        
        reload_mock.assert_called()
        # Verify update to false
        mock_conn.execute.assert_called() # Select and Update

    
def test_check_reload_signal_false(mock_scheduler_deps):
    service = SchedulerService()
    
    # Mock DB return false
    mock_conn = mock_scheduler_deps['db'].return_value
    mock_conn.execute.return_value.fetchone.return_value = ['false']
    
    with patch.object(service, 'reload_schedule') as reload_mock:
        service._check_reload_signal()
        reload_mock.assert_not_called()

def test_job_weekly_report(mock_scheduler_deps):
    service = SchedulerService()
    with patch.object(service, 'get_all_users', return_value=['u1']):
        service.job_weekly_report()
        mock_scheduler_deps['subprocess'].assert_called()
        args, _ = mock_scheduler_deps['subprocess'].call_args
        assert "weekly" in args[0]

def test_job_monthly_refinement(mock_scheduler_deps):
    service = SchedulerService()
    # Mock date to be 1st of month
    with patch('src.services.scheduler_service.get_current_time') as time_mock:
        time_mock.return_value.day = 1
        
        # job_monthly_refinement calls subprocess run
        service.job_monthly_refinement()
        
        # Verify subprocess call to refinement.py
        mock_scheduler_deps['subprocess'].assert_called()
        args, _ = mock_scheduler_deps['subprocess'].call_args
        assert "refinement.py" in str(args[0])
