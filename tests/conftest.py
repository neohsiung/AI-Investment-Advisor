import pytest
from unittest.mock import MagicMock, patch
import sys

@pytest.fixture
def mock_streamlit_module():
    """
    Safely mock streamlit module directly in sys.modules for the duration of the test.
    Restores original module (if any) afterwards.
    """
    mock_st = MagicMock()
    # Mock commonly accessed submodules/attributes
    mock_st.sidebar = MagicMock()
    mock_st.session_state = {}
    
    # We patch sys.modules to inject our mock
    # patch.dict handles restoration automatically
    with patch.dict(sys.modules, {'streamlit': mock_st, 'streamlit.components.v1': MagicMock()}):
        yield mock_st
