import pytest
from unittest.mock import MagicMock, patch, mock_open
from src.agents.engineer import SystemEngineerAgent

@pytest.fixture
def mock_deps():
    with patch('src.agents.engineer.get_db_connection') as db_mock, \
         patch('src.agents.engineer.BaseAgent._call_real_llm') as llm_mock:
        yield {
            "db": db_mock,
            "llm": llm_mock
        }

def test_analyze_optimization_needs_basic(mock_deps):
    agent = SystemEngineerAgent()
    report = """
    # CIO Report
    ...
    ## System Optimization Feedback
    The Momentum agent is too aggressive.
    """
    needs = agent.analyze_optimization_needs(report)
    assert len(needs) == 1
    assert "Momentum agent is too aggressive" in needs[0]['raw_feedback']

def test_analyze_optimization_needs_hr_request(mock_deps):
    agent = SystemEngineerAgent()
    report = """
    [HR_REQUEST] Replace Agent: Momentum (Reason: Idle for 7 days)
    """
    needs = agent.analyze_optimization_needs(report)
    assert len(needs) == 1
    assert needs[0]['target_agent'] == "Momentum"
    assert "Idle for 7 days" in needs[0]['raw_feedback']

def test_analyze_optimization_needs_empty(mock_deps):
    agent = SystemEngineerAgent()
    report = "No feedback here."
    needs = agent.analyze_optimization_needs(report)
    assert len(needs) == 0

def test_get_schedule_config(mock_deps):
    agent = SystemEngineerAgent()
    mock_conn = mock_deps['db'].return_value
    mock_conn.execute.return_value.fetchall.return_value = [
        ('schedule_daily', '09:00'),
        ('schedule_weekly', '10:00')
    ]
    
    config = agent.get_schedule_config()
    assert config['schedule_daily'] == '09:00'
    assert config['schedule_weekly'] == '10:00'

def test_set_schedule_config(mock_deps):
    agent = SystemEngineerAgent()
    mock_conn = mock_deps['db'].return_value
    
    agent.set_schedule_config("08:00", "09:00")
    
    # Should execute insert/replace
    assert mock_conn.execute.call_count >= 2
    mock_conn.commit.assert_called()

def test_run_with_optimization(mock_deps):
    agent = SystemEngineerAgent()
    
    # Mock file reading for original prompt
    with patch("builtins.open", mock_open(read_data="Original Prompt")):
        # Mock LLM response
        mock_deps['llm'].return_value = '{"optimized_prompt": "New Prompt", "diff_explanation": "Improved stability"}'
        
        context = {
            "cio_report": "## System Optimization Feedback\nFix Momentum."
        }
        
        # We also need to mock os.path.exists to true
        with patch("os.path.exists", return_value=True):
            # And mock _save_prompt to avoid actual writing (though mock_open handles it partly, we might need explicit separate mock if we care about writemode)
            # Actually mock_open handles write too.
            
            result = agent.run(context)
            
            assert "Optimized Momentum" in result
            assert "Improved stability" in result
            
            # Verify DB log
            mock_deps['db'].return_value.execute.assert_called()
            
def test_run_no_optimization_needed(mock_deps):
    agent = SystemEngineerAgent()
    context = {"cio_report": "Nothing to do."}
    result = agent.run(context)
    assert "No optimization feedback found" in result

def test_run_optimization_failure(mock_deps):
    agent = SystemEngineerAgent()
    with patch("builtins.open", mock_open(read_data="Original")):
        mock_deps['llm'].return_value = "Invalid JSON"
        with patch("os.path.exists", return_value=True):
            result = agent.run({"cio_report": "## System Optimization Feedback\nDo it."})
            assert "Failed to parse" in result
