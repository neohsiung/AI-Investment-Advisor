import pytest
from unittest.mock import MagicMock, patch, mock_open
import sys
import importlib

# Do not import ui here globally to allow fixture to mock sys.modules
# from src.utils import ui

class TestUI:
    
    @pytest.fixture
    def ui_module(self, mock_streamlit_module):
        # Ensure it's imported
        if 'src.utils.ui' in sys.modules:
             importlib.reload(sys.modules['src.utils.ui'])
             return sys.modules['src.utils.ui']
        else:
             return importlib.import_module('src.utils.ui')


    def test_get_auto_theme_forced_light(self, ui_module):
        """Test that get_auto_theme always returns light."""
        assert ui_module.get_auto_theme() == "light"

    def test_load_theme_css_defaults_light(self, ui_module):
        """Test load_theme_css defaults."""
        with patch('builtins.open', mock_open(read_data="body { color: black; }")) as mock_file:
            st_mock = sys.modules['streamlit']
            
            ui_module.load_theme_css()
            
            # verify it tries to open light_theme.css
            args, _ = mock_file.call_args
            assert "light_theme.css" in args[0]
            st_mock.markdown.assert_called()

    def test_render_sidebar_structure(self, ui_module):
        """Test sidebar rendering structure."""
        st_mock = sys.modules['streamlit']
        
        # Helper for dict/attr access
        class MockSessionState(dict):
            def __getattr__(self, key): return self.get(key)
            def __setattr__(self, key, value): self[key] = value
            
        st_mock.session_state = MockSessionState()
        
        user = {'name': 'Test User', 'email': 'test@example.com', 'picture': 'pic.jpg'}
        
        ui_module.render_sidebar(user)
        
        # Verify sidebar calls
        # Let's check: ui.py forces light. render_sidebar might strictly display user info.
