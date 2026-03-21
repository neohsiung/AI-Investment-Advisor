
import pytest
from unittest.mock import MagicMock, patch
import os
from src.agents.base_agent import BaseAgent

# Mock Concrete Implementation of Abstract BaseAgent
class ConcreteAgent(BaseAgent):
    def run(self, context):
        pass

@pytest.fixture
def mock_settings_repo():
    repo = MagicMock()
    # Mocking get_global to return a list of objects that behave like SQLAlchemy rows or dicts
    # In BaseAgent, it expects objects with _mapping or tuple access, or just dicts if we're lucky with the implementation details.
    # Let's check BaseAgent._load_config_from_db again.
    # It tries `row._mapping['key']` or `row[0]`.
    return repo

def test_config_priority_db_over_env(mock_settings_repo):
    """
    Test that DB settings take precedence over Environment variables.
    """
    # Setup Env
    with patch.dict(os.environ, {"AI_PROVIDER": "EnvProvider", "API_KEY": "EnvKey", "AI_MODEL": "EnvModel"}):
        # Setup DB (Mock returns from get_global)
        # We need to simulate the row structure. BaseAgent handles:
        # row._mapping['key'] / row._mapping['value'] OR row[0] / row[1]
        
        # Let's use simple named tuples or objects for rows
        class MockRow:
            def __init__(self, k, v):
                self._mapping = {'key': k, 'value': v}
        
        mock_rows = [
            MockRow("AI_PROVIDER", "DBProvider"),
            MockRow("API_KEY", "DBKey"),
            MockRow("AI_MODEL", "DBModel")
        ]
        
        mock_settings_repo.get_all.return_value = mock_rows

        # Initialize Agent
        with patch.object(BaseAgent, '_load_prompt', return_value="System Prompt"):
             agent = ConcreteAgent(name="TestAgent", prompt_path="tests/fixtures/fake_prompt.txt", 
                                   user_id="test_user", settings_repo=mock_settings_repo)
        
        # Verify Config
        
        # Verify Config
        assert agent.config["provider"] == "DBProvider"
        assert agent.config["api_key"] == "DBKey"
        assert agent.config["model"] == "DBModel"

def test_config_fallback_to_env(mock_settings_repo):
    """
    Test that if DB is empty, it falls back to Environment variables.
    """
    with patch.dict(os.environ, {"AI_PROVIDER": "EnvProvider", "API_KEY": "EnvKey"}):
        mock_settings_repo.get_all.return_value = []
        
        # Create a dummy prompt file if needed or mock _load_prompt
        with patch.object(BaseAgent, '_load_prompt', return_value="System Prompt"):
             agent = ConcreteAgent(name="TestAgent", prompt_path="dummy", settings_repo=mock_settings_repo)

        assert agent.config["provider"] == "EnvProvider"
        assert agent.config["api_key"] == "EnvKey"

def test_user_specific_override(mock_settings_repo):
    """
    Test that User-specific DB settings override Global DB settings.
    """
    class MockRow:
        def __init__(self, k, v):
            self._mapping = {'key': k, 'value': v}

    # In modern architecture, BaseAgent only calls get_all(user_id)
    # Priority is Env < DB. 
    user_rows = [MockRow("AI_PROVIDER", "UserProvider")]
    mock_settings_repo.get_all.return_value = user_rows
    
    with patch.object(BaseAgent, '_load_prompt', return_value="System Prompt"):
        agent = ConcreteAgent(name="TestAgent", prompt_path="dummy", user_id="test_user", settings_repo=mock_settings_repo)
    
    assert agent.config["provider"] == "UserProvider"
