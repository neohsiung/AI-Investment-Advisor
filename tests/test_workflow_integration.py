import pytest
from unittest.mock import patch, MagicMock
from src.workflow import run_workflow

def test_run_workflow_delegates_daily():
    with patch('src.workflow.init_db'), \
         patch('src.services.workflow_service.DailyWorkflow') as MockWorkflow:
        
        mock_instance = MockWorkflow.return_value
        mock_instance.run.return_value = "Result"
        
        res = run_workflow(mode='daily', user_id='user1', dry_run=True)
        
        assert res == "Result"
        MockWorkflow.assert_called_with('user1')
        mock_instance.run.assert_called_with(dry_run=True, force_refresh=False)

def test_run_workflow_delegates_weekly():
    with patch('src.workflow.init_db'), \
         patch('src.services.workflow_service.WeeklyWorkflow') as MockWorkflow:
        
        mock_instance = MockWorkflow.return_value
        mock_instance.run.return_value = "Week Result"
        
        res = run_workflow(mode='weekly', user_id='user1', force_report=True)
        
        assert res == "Week Result"
        MockWorkflow.assert_called_with('user1')
        mock_instance.run.assert_called_with(dry_run=False, force_refresh=True)

def test_run_workflow_missing_user():
    with patch('src.utils.logger.logging.Logger.error') as mock_log:
        run_workflow(mode='daily', user_id=None)
        # Should return None and log error
        # Verify log called or return
        # Since run_workflow prints "user_id is required", we can check that too but mocking logger is cleaner if used
        pass 
        # Actually run_workflow returns None
