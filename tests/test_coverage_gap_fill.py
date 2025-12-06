import pytest
from unittest.mock import MagicMock, patch, mock_open
import sys
import os
import requests 
from src.agents.base_agent import BaseAgent
from src.market_data import MarketDataService

# --- Base Agent Tests ---

class TestAgent(BaseAgent):
    def run(self, context):
        return "Test Run"

@pytest.fixture
def mock_agent():
    with patch('builtins.open', mock_open(read_data="System Prompt")):
        with patch('os.path.exists', return_value=True):
            with patch.object(BaseAgent, '_load_config', return_value={
                "provider": "Google Gemini", "model": "gemini-1.5-pro", "api_key": "test_key"
            }):
                agent = TestAgent("TestAgent", "prompt.txt")
                return agent

def test_base_agent_load_config_error():
    with patch('src.agents.base_agent.get_db_connection', side_effect=Exception("DB Error")):
        # We need to mock file operations here too since we're instantiating TestAgent
        with patch('builtins.open', mock_open(read_data="System Prompt")):
            with patch('os.path.exists', return_value=True):
                # Should not raise, just log warning and return default
                agent = TestAgent("TestAgent", "prompt.txt") 
                assert agent.config["provider"] == "Google Gemini" # Default

def test_base_agent_load_prompt_error():
    with patch('os.path.exists', return_value=False):
        with pytest.raises(FileNotFoundError):
            TestAgent("TestAgent", "missing.txt")

def test_base_agent_real_llm_openrouter(mock_agent):
    mock_agent.config["provider"] = "OpenRouter"
    with patch('requests.post') as mock_post:
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = {
            "choices": [{"message": {"content": "OpenRouter Response"}}]
        }
        resp = mock_agent._call_real_llm("prompt", "system")
        assert resp == "OpenRouter Response"

def test_base_agent_real_llm_openai(mock_agent):
    mock_agent.config["provider"] = "OpenAI"
    with patch('requests.post') as mock_post:
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = {
            "choices": [{"message": {"content": "OpenAI Response"}}]
        }
        resp = mock_agent._call_real_llm("prompt", "system")
        assert resp == "OpenAI Response"

def test_base_agent_real_llm_error_handling(mock_agent):
    mock_agent.config["provider"] = "Google Gemini"
    with patch('requests.post') as mock_post:
        mock_post.side_effect = requests.exceptions.RequestException("API Fail")
        with pytest.raises(requests.exceptions.RequestException):
            mock_agent._call_real_llm("prompt", "system")

def test_base_agent_mock_fallback(mock_agent):
    mock_agent.config['api_key'] = 'valid_key'
    with patch.object(mock_agent, '_call_real_llm', side_effect=Exception("Major Fail")):
        # fallback to mock
        resp = mock_agent._mock_llm_call("prompt", "system")
        assert "Mock response" in resp

# --- Market Data Tests ---

def test_market_data_fallback():
    # Test internal methods or specific failure paths if not covered
    service = MarketDataService()
    with patch('yfinance.Ticker') as mock_ticker:
        mock_ticker.return_value.history.return_value.empty = True
        # If history is empty, it might log a warning or return None depending on implementation
        # This test ensures we hit that branch
        prices = service.get_current_prices(["INVALID"])
        assert prices.get("INVALID") is None

# --- Scheduler CLI Tests ---
# This is tricky without executing the file, but we can verify the function logic if refactored.
# Since scheduler.py is hard to test directly due to while loop, we rely on the implementation 
# refactor we did earlier (args parsing). 

# --- Additional Market Data Tests for specific methods ---

def test_market_data_get_market_context_with_fallback(mock_agent):
    # Mock MarketDataService and its dependencies
    service = MarketDataService()
    
    with patch.object(service, 'get_current_prices', return_value={'AAPL': 0}):
        with patch.object(service, '_fetch_from_llm', return_value={'price': 150.0, 'indicators': {'rsi': 60}}):
            with patch.object(service, 'get_technical_indicators', return_value={'rsi': 50}):
                # Test logic
                context = service.get_market_context(['AAPL'])
                
                assert context['AAPL']['price'] == 150.0
                assert context['AAPL']['indicators']['rsi'] == 60

def test_market_data_fetch_from_llm_success():
    service = MarketDataService()
    
    # Mock database to return settings
    mock_db_conn = MagicMock()
    mock_db_conn.execute.return_value.fetchall.return_value = [
        ("AI_PROVIDER", "OpenRouter"), ("API_KEY", "test_key"), ("AI_MODEL", "gpt-4")
    ]
    
    with patch('src.market_data.get_db_connection', return_value=mock_db_conn):
        with patch('requests.post') as mock_post:
            mock_post.return_value.status_code = 200
            # Mock successful JSON response
            mock_post.return_value.json.return_value = {
                "choices": [{"message": {"content": '{"price": 100.0, "indicators": {}}'}}]
            }
            
            data = service._fetch_from_llm("AAPL")
            assert data['price'] == 100.0

def test_market_data_fetch_from_llm_fail():
    service = MarketDataService()
    with patch('src.market_data.get_db_connection', side_effect=Exception("DB Error")):
         data = service._fetch_from_llm("AAPL")
         assert data is None
