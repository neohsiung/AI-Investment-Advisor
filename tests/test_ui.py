import pytest
from unittest.mock import MagicMock, patch, mock_open
import sys
import importlib

class MockSessionState(dict):
    """Mock Streamlit SessionState supporting both item and attribute access."""
    def __getattr__(self, key):
        if key in self: return self[key]
        raise AttributeError(f"No such attribute: {key}")
    def __setattr__(self, key, value): self[key] = value

class TestUI:
    
    @pytest.fixture
    def ui_module(self, mock_streamlit_module):
        # Ensure it's imported
        if 'src.utils.ui' in sys.modules:
             importlib.reload(sys.modules['src.utils.ui'])
             return sys.modules['src.utils.ui']
        else:
             return importlib.import_module('src.utils.ui')

    def test_load_design_system_css(self, ui_module):
        """Test that load_design_system_css calls st.markdown with CSS variables."""
        st_mock = sys.modules['streamlit']
        mock_state = MockSessionState()
        with patch.object(st_mock, 'session_state', mock_state), \
             patch.object(st_mock, 'markdown') as mock_md, \
             patch('builtins.open', mock_open(read_data=".test { color: red; }")), \
             patch('os.path.exists', return_value=True):
            ui_module.load_design_system_css()
            mock_md.assert_called()

    def test_load_theme_css_defaults_light(self, ui_module):
        """Test load_theme_css defaults."""
        st_mock = sys.modules['streamlit']
        mock_state = MockSessionState({'theme': 'light'})
        with patch.object(st_mock, 'session_state', mock_state), \
             patch.object(st_mock, 'markdown') as mock_md, \
             patch('builtins.open', mock_open(read_data="body { color: black; }")), \
             patch('os.path.exists', return_value=True):
            ui_module.load_theme_css()
            mock_md.assert_called()

    def test_render_sidebar_structure(self, ui_module):
        """Test sidebar rendering structure with hyper-minimalist preference bar."""
        st_mock = sys.modules['streamlit']
        st_mock.session_state = MockSessionState({'theme': 'light'})
        st_mock.columns.return_value = [MagicMock(), MagicMock()]
        
        user = {'name': 'Test User', 'email': 'test@example.com', 'picture': 'pic.jpg'}
        
        with patch('src.auth.auth_manager') as mock_auth:
            ui_module.render_sidebar(user)
        
        # Verify sidebar elements
        st_mock.sidebar.__enter__.assert_called()
        # Verify Profile/Settings link
        st_mock.page_link.assert_any_call("pages/06_Settings.py", label="T. Test U...", icon=":material/account_circle:", help="User Settings", use_container_width=False)
        # Verify columns allocation
        st_mock.columns.assert_called_with([3.5, 1])
