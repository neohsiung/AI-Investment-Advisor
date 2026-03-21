import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from services.scheduler.src.app import run_workflow

@pytest.fixture
def anyio_backend():
    return 'asyncio'

@pytest.mark.anyio
async def test_run_workflow_delegates_daily():
    with patch('services.scheduler.src.app.init_db'), \
         patch('src.services.workflow_service.DailyWorkflow') as MockWorkflow:
        
        mock_instance = MockWorkflow.return_value
        mock_instance.run = AsyncMock(return_value="Result")
        
        res = await run_workflow(mode='daily', user_id='user1', dry_run=True)
        
        assert res == "Result"
        MockWorkflow.assert_called_with('user1')
        mock_instance.run.assert_called_with(dry_run=True, force_refresh=False)

@pytest.mark.anyio
async def test_run_workflow_delegates_weekly():
    with patch('services.scheduler.src.app.init_db'), \
         patch('src.services.workflow_service.WeeklyWorkflow') as MockWorkflow:
        
        mock_instance = MockWorkflow.return_value
        mock_instance.run = AsyncMock(return_value="Week Result")
        
        res = await run_workflow(mode='weekly', user_id='user1', force_report=True)
        
        assert res == "Week Result"
        MockWorkflow.assert_called_with('user1')
        mock_instance.run.assert_called_with(dry_run=False, force_refresh=True)

@pytest.mark.anyio
async def test_run_workflow_missing_user():
    with patch('services.scheduler.src.app.init_db'), \
         patch('src.utils.logger.logging.Logger.error') as mock_log:
        res = await run_workflow(mode='daily', user_id=None)
        # Should return None and log error
        assert res is None
