import pytest
from unittest.mock import MagicMock, patch, mock_open
import sys

def test_cio_agent_init():
    # Patch sys.modules dynamically
    with patch.dict('sys.modules', {
        "google": MagicMock(),
        "google.generativeai": MagicMock(),
        "openai": MagicMock(),
        "src.utils.logger": MagicMock(),
    }):
        # Import inside the patched context
        # We might need to ensure src.agents.cio isn't already loaded
        if 'src.agents.cio' in sys.modules:
            del sys.modules['src.agents.cio']
            
        from src.agents.cio import CIOAgent
        
        with patch("builtins.open", mock_open(read_data="Prompt Content")), \
             patch("src.agents.base_agent.BaseAgent._load_config", return_value={"provider": "OpenAI"}), \
             patch("src.agents.cio.CIOAgent._load_config", return_value={"provider": "OpenAI"}):
             
            # Mock repositories injection
            mock_settings = MagicMock()
            mock_trans = MagicMock()
            
            agent = CIOAgent(
                settings_repo=mock_settings, 
                transaction_repo=mock_trans
            )
            assert agent is not None
            assert agent.name == "CIO"
            
            with patch.object(agent, 'call_llm', return_value='{"decision": "HOLD"}'):
                pass
