import pytest
from unittest.mock import MagicMock, patch, mock_open
from src.agents.engineer import SystemEngineerAgent
from src.repositories.settings_repository import ISettingsRepository
from src.repositories.prompt_repository import IPromptRepository
import json

@pytest.fixture
def mock_settings_repo():
    repo = MagicMock(spec=ISettingsRepository)
    repo.get_by_prefix.return_value = []
    return repo

@pytest.fixture
def mock_prompt_repo():
    repo = MagicMock(spec=IPromptRepository)
    return repo

@pytest.fixture
def agent(mock_settings_repo, mock_prompt_repo):
    with patch('src.agents.base_agent.BaseAgent._load_prompt', return_value="Engineer Prompt"):
         # Mock BaseAgent config load implicit in init
         with patch.object(SystemEngineerAgent, '_load_config', return_value={"provider": "OpenAI"}):
             mock_state = MagicMock()
             return SystemEngineerAgent(user_id="test_user", settings_repo=mock_settings_repo, prompt_repo=mock_prompt_repo, state_repo=mock_state)

def test_analyze_optimization_needs_basic(agent):
    report = """
    # CIO Report
    ...
    ## System Optimization Feedback
    The Momentum agent is too aggressive.
    """
    needs = agent.analyze_optimization_needs(report)
    assert len(needs) == 1
    assert "Momentum agent is too aggressive" in needs[0]['raw_feedback']

def test_analyze_optimization_needs_hr_request(agent):
    report = """
    [HR_REQUEST] Replace Agent: Momentum (Reason: Idle for 7 days)
    """
    needs = agent.analyze_optimization_needs(report)
    assert len(needs) == 1
    assert needs[0]['target_agent'] == "Momentum"
    assert "Idle for 7 days" in needs[0]['raw_feedback']

def test_analyze_optimization_needs_empty(agent):
    report = "No feedback here."
    needs = agent.analyze_optimization_needs(report)
    assert len(needs) == 0

def test_get_schedule_config(agent, mock_settings_repo):
    # Mock Repo Return
    row1 = MagicMock()
    # Mock _mapping access
    row1._mapping = {'key': 'schedule_daily', 'value': '09:00'}
    
    row2 = MagicMock()
    row2._mapping = {'key': 'schedule_weekly', 'value': '10:00'}

    mock_settings_repo.get_all.return_value = [("schedule_daily", "09:00"), ("schedule_weekly", "10:00")]
    
    config = agent.get_schedule_config()
    assert config['schedule_daily'] == '09:00'
    assert config['schedule_weekly'] == '10:00'

def test_set_schedule_config(agent, mock_settings_repo):
    agent.set_schedule_config("08:00", "09:00")
    assert mock_settings_repo.set.call_count == 3
    mock_settings_repo.set.assert_any_call(agent.user_id, "schedule_daily", "08:00")

@pytest.mark.asyncio
async def test_run_with_optimization(agent, mock_prompt_repo):
    context = {"cio_report": "## System Optimization Feedback\nFix Momentum."}
    
    from unittest.mock import AsyncMock
    with patch.object(agent, '_call_real_llm', new_callable=AsyncMock) as mock_llm:
        mock_llm.return_value = '{"optimized_prompt": "New Prompt", "diff_explanation": "Improved stability"}'
        with patch.object(agent, '_read_prompt', return_value="Original Prompt"):
             with patch.object(agent, '_save_prompt'):
                 result = await agent.run(context)
                 assert len(result) > 0
                 assert result[0]['target_agent'] == 'Momentum'
                 mock_prompt_repo.log_change.assert_called_once()

@pytest.mark.asyncio
async def test_run_no_optimization_needed(agent):
    context = {"cio_report": "Nothing to do."}
    result = await agent.run(context)
    assert result == []

@pytest.mark.asyncio
async def test_run_optimization_failure(agent):
    from unittest.mock import AsyncMock
    with patch.object(agent, '_call_real_llm', new_callable=AsyncMock) as mock_llm:
         mock_llm.return_value = "Invalid JSON"
         with patch.object(agent, '_read_prompt', return_value="Original"):
             result = await agent.run({"cio_report": "## System Optimization Feedback\nDo it."})
             result_str = str(result)
             assert "error" in result_str.lower() or "failed" in result_str.lower()
