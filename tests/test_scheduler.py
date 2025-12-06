import pytest
from unittest.mock import patch, MagicMock
from src.scheduler import job_daily_check, job_weekly_report, job_monthly_refinement
from datetime import datetime

@patch('src.scheduler.subprocess.run')
@patch('src.scheduler.log_scheduler_event')
@patch('src.scheduler.get_current_time')
def test_job_daily_check_weekday(mock_time, mock_log, mock_run):
    # Mock Monday (0)
    mock_time.return_value = datetime(2023, 1, 2, 9, 0, 0) # Monday
    
    job_daily_check()
    
    mock_run.assert_called_once()
    args, _ = mock_run.call_args
    assert "daily" in args[0]
    assert mock_log.call_count == 2 # Started, Completed

@patch('src.scheduler.subprocess.run')
@patch('src.scheduler.log_scheduler_event')
@patch('src.scheduler.get_current_time')
def test_job_daily_check_saturday(mock_time, mock_log, mock_run):
    # Mock Saturday (5)
    mock_time.return_value = datetime(2023, 1, 7, 9, 0, 0) # Saturday
    
    job_daily_check()
    
    mock_run.assert_not_called()

@patch('src.scheduler.subprocess.run')
@patch('src.scheduler.log_scheduler_event')
def test_job_weekly_report(mock_log, mock_run):
    job_weekly_report()
    
    mock_run.assert_called_once()
    args, _ = mock_run.call_args
    assert "weekly" in args[0]
    assert mock_log.call_count == 2

@patch('src.scheduler.subprocess.run')
@patch('src.scheduler.log_scheduler_event')
def test_job_monthly_refinement(mock_log, mock_run):
    job_monthly_refinement()
    
    mock_run.assert_called_once()
    args, _ = mock_run.call_args
    assert "refinement.py" in args[0][1]
    assert mock_log.call_count == 2
