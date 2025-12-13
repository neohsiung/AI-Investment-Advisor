import pytest
from unittest.mock import MagicMock, patch
from src.scheduler import get_all_users, check_monthly_job, run_scheduler_loop
from datetime import datetime

@patch('src.scheduler.get_db_connection')
def test_get_all_users_success(mock_conn):
    # Mock result with some users
    mock_result = MagicMock()
    mock_result.fetchall.return_value = [("user1@example.com",), ("user2@example.com",)]
    mock_conn.return_value.execute.return_value = mock_result
    
    users = get_all_users()
    assert len(users) == 2
    assert "user1@example.com" in users
    assert "user2@example.com" in users

@patch('src.scheduler.get_db_connection')
def test_get_all_users_empty(mock_conn):
    # Mock result with no users
    mock_result = MagicMock()
    mock_result.fetchall.return_value = []
    mock_conn.return_value.execute.return_value = mock_result
    
    users = get_all_users()
    assert len(users) == 0

@patch('src.scheduler.get_db_connection')
def test_get_all_users_exception(mock_conn):
    # Mock database error
    mock_conn.return_value.execute.side_effect = Exception("DB Error")
    
    users = get_all_users()
    assert len(users) == 0

@patch('src.scheduler.get_current_time')
@patch('src.scheduler.job_monthly_refinement')
def test_check_monthly_job_triggers(mock_job, mock_time):
    # 1st of month
    mock_time.return_value = datetime(2023, 1, 1, 10, 0, 0)
    check_monthly_job()
    mock_job.assert_called_once()

@patch('src.scheduler.get_current_time')
@patch('src.scheduler.job_monthly_refinement')
def test_check_monthly_job_skips(mock_job, mock_time):
    # 2nd of month
    mock_time.return_value = datetime(2023, 1, 2, 10, 0, 0)
    check_monthly_job()
    mock_job.assert_not_called()

@patch('src.agents.engineer.SystemEngineerAgent')
@patch('schedule.every')
@patch('schedule.run_pending')
@patch('src.scheduler.time.sleep')
def test_run_scheduler_loop(mock_sleep, mock_run_pending, mock_every, mock_agent_cls):
    # Setup mocks
    mock_agent = mock_agent_cls.return_value
    mock_agent.get_schedule_config.return_value = {"schedule_daily": "08:00", "schedule_weekly": "10:00"}
    
    # Break loop after one iteration
    mock_sleep.side_effect = StopIteration
    
    try:
        run_scheduler_loop()
    except StopIteration:
        pass
        
    # Verify logic
    assert mock_agent.get_schedule_config.called
    assert mock_every.call_count >= 3 # Daily, Weekly, Monthly
    mock_run_pending.assert_called_once()
