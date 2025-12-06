import pytest
from unittest.mock import MagicMock, patch, mock_open
from src.agents.cio import CIOAgent
from src.agents.macro import MacroAgent
from src.agents.engineer import SystemEngineerAgent
import json
import os

@patch('src.agents.base_agent.get_db_connection')
def test_cio_agent(mock_db):
    mock_db.return_value.cursor.return_value.fetchall.return_value = []
    
    # Mock read_sql to return some tickers
    with patch('pandas.read_sql') as mock_read_sql:
        mock_df = MagicMock()
        mock_df.empty = False
        mock_df.__getitem__.return_value.tolist.return_value = ['AAPL', 'TSLA'] # Non-ETF
        mock_read_sql.return_value = mock_df
        
        # Patch _load_prompt instead of open() to avoid side effects
        with patch('src.agents.base_agent.BaseAgent._load_prompt', return_value="CIO Prompt"):
             agent = CIOAgent(use_cache=False)
                
             with patch.object(agent, '_mock_llm_call', return_value="Mock response"):
                 context = {"leverage_ratio": 1.2, "macro_report": "Good"}
                 result = agent.run(context)
                 assert "Mock" in result
                 assert "(Mock)" in result

@patch('src.agents.base_agent.get_db_connection')
def test_macro_agent(mock_db):
    mock_db.return_value.cursor.return_value.fetchall.return_value = []
    
    # Patch _load_prompt
    with patch('src.agents.base_agent.BaseAgent._load_prompt', return_value="Macro Prompt"):
        agent = MacroAgent(use_cache=False)
        
        with patch.object(agent, '_mock_llm_call', return_value="Mock response"):
            result = agent.run({"macro_data": "VIX High"})
            assert "(Mock)" in result

@patch('src.agents.base_agent.get_db_connection')
def test_engineer_agent(mock_db):
    mock_db.return_value.cursor.return_value.fetchall.return_value = []
    
    with patch('src.agents.base_agent.BaseAgent._load_prompt', return_value="Engineer Prompt"):
        agent = SystemEngineerAgent(use_cache=False)
        
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
                 # Mock _save_prompt and _log_history
                 # Using create=True for methods that might be dynamically defined or if strict checking fails
                 with patch.object(agent, '_save_prompt', create=True), patch.object(agent, '_log_history', create=True):
                    result = agent.run({"cio_report": report})
                    assert "Optimized Momentum" in result
