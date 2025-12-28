import pytest
from unittest.mock import MagicMock, patch, mock_open
from src.agents.cio import CIOAgent
from src.agents.macro import MacroAgent
from src.agents.engineer import SystemEngineerAgent
from src.repositories.settings_repository import ISettingsRepository
from src.repositories.agent_state_repository import IAgentStateRepository
import json
import os

@pytest.fixture
def mock_settings_repo():
    repo = MagicMock(spec=ISettingsRepository)
    repo.get_global.return_value = []
    repo.get_all.return_value = []
    return repo

@pytest.fixture
def mock_state_repo():
    repo = MagicMock(spec=IAgentStateRepository)
    repo.get_state.return_value = None
    return repo

def test_cio_agent(mock_settings_repo, mock_state_repo):
    # Mock Transaction Repo needed for CIO
    mock_trans_repo = MagicMock()
    # Mock holdings
    mock_trans_repo.get_user_tickers.return_value = ['AAPL', 'TSLA']
    mock_trans_repo.get_holdings_summary.return_value = [('AAPL', 10), ('TSLA', 5)]
    mock_trans_repo.get_latest_leverage.return_value = 1.2

    # Patch _load_prompt instead of open() to avoid side effects
    with patch('src.agents.base_agent.BaseAgent._load_prompt', return_value="CIO Prompt"):
         agent = CIOAgent(use_cache=False, transaction_repo=mock_trans_repo, 
                          settings_repo=mock_settings_repo, state_repo=mock_state_repo)

         with patch.object(agent, '_mock_llm_call', return_value="Mock response"):
             context = {"user_id": "test_user", "leverage_ratio": 1.2, "macro_report": "Good"}
             result = agent.run(context)
             assert "Mock" in result

def test_macro_agent(mock_settings_repo, mock_state_repo):
    with patch('src.agents.base_agent.BaseAgent._load_prompt', return_value="Macro Prompt"):
        agent = MacroAgent(use_cache=False, settings_repo=mock_settings_repo, state_repo=mock_state_repo)

        with patch.object(agent, '_mock_llm_call', return_value="Test Result"):
            result = agent.run({"macro_data": "VIX High"})
            assert "Test Result" in result

@pytest.fixture
def mock_prompt_repo():
    return MagicMock()

def test_engineer_agent(mock_settings_repo, mock_state_repo, mock_prompt_repo):
    with patch('src.agents.base_agent.BaseAgent._load_prompt', return_value="Engineer Prompt"):
        agent = SystemEngineerAgent(use_cache=False, settings_repo=mock_settings_repo, 
                                    state_repo=mock_state_repo, prompt_repo=mock_prompt_repo)

        # Test analyze_optimization_needs
        report = "Section 1...\nSystem Optimization Feedback\nPlease optimize Momentum.\n"
        needs = agent.analyze_optimization_needs(report)
        assert needs[0]['raw_feedback'].strip() == "Please optimize Momentum."

        # Test run (Mock LLM interaction)
        with patch.object(agent, '_call_real_llm') as mock_llm:
            # Return valid JSON for optimization
            mock_llm.return_value = json.dumps({
                "optimized_prompt": "New Prompt",
                "diff_explanation": "Improved clarity"
            })

            # Mock _load_prompt defined in BaseAgent (SystemEngineerAgent inherits it)
            with patch.object(agent, '_load_prompt', return_value="Old Prompt"):
                 # Mock _save_prompt
                 # We no longer need to patch _log_prompt_change as it uses repo now! (Wait, did I remove the patch?)
                 # The logic uses self.prompt_repo.log_change.
                 # mocking _save_prompt (file write) is still good.
                 with patch.object(agent, '_save_prompt', create=True):
                    result = agent.run({"cio_report": report})
                    # Check list content
                    assert isinstance(result, list)
                    assert len(result) > 0
                    assert result[0]['target_agent'] == 'Momentum'
                    
                    # Verify Repo usage
                    mock_prompt_repo.log_change.assert_called_once()
