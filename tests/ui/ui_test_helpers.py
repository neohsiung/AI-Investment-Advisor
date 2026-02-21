"""
UI Test Utilities for Streamlit Pages.
Streamlit 頁面測試工具。
"""
import pytest
from unittest.mock import MagicMock, patch
from typing import Dict, Any


class StreamlitMocker:
    """Helper class to mock Streamlit components."""
    
    def __init__(self):
        self.session_state = {}
        self.widgets = {}
        
    def mock_session_state(self, initial_state: Dict[str, Any] = None):
        """Create a mock session state."""
        if initial_state:
            self.session_state.update(initial_state)
        return self.session_state
    
    def mock_text_area(self, key: str, default=""):
        """Mock st.text_area."""
        value = self.session_state.get(key, default)
        self.widgets[key] = value
        return value
    
    def mock_text_input(self, label: str, value="", key=None):
        """Mock st.text_input."""
        if key:
            return self.session_state.get(key, value)
        return value
    
    def mock_button(self, label: str, key=None):
        """Mock st.button - returns True once per test."""
        if key:
            return self.widgets.get(f"button_{key}", False)
        return False
    
    def mock_checkbox(self, label: str, value=False, key=None):
        """Mock st.checkbox."""
        if key:
            return self.session_state.get(key, value)
        return value
    
    def mock_selectbox(self, label: str, options, index=0, key=None):
        """Mock st.selectbox."""
        if key and key in self.session_state:
            return self.session_state[key]
        return options[index] if options else None


@pytest.fixture
def streamlit_mocker():
    """Fixture providing Streamlit mocker."""
    return StreamlitMocker()


@pytest.fixture
def mock_settings_service():
    """Fixture providing mock SettingsService."""
    mock = MagicMock()
    mock.get_all_settings.return_value = {}
    mock.get_setting.return_value = None
    mock.save_setting.return_value = True
    return mock


@pytest.fixture
def ui_session_state():
    """Fixture providing standard UI session state."""
    return {
        'user_id': 'test_user@example.com',
        'settings_changed': False,
        'show_success': False,
        'show_error': False
    }


def create_streamlit_context(session_state: Dict[str, Any] = None):
    """
    Create a complete Streamlit mocking context.
    
    Usage:
        with create_streamlit_context({'user_id': 'test'}):
            from services.dashboard.src.pages.settings_tabs import some_tab
            some_tab.render()
    """
    import streamlit as st
    
    # Mock session state
    if session_state:
        for key, value in session_state.items():
            st.session_state[key] = value
    
    # Create mock context
    patches = {
        'sidebar': MagicMock(),
        'write': MagicMock(),
        'markdown': MagicMock(),
        'success': MagicMock(),
        'error': MagicMock(),
        'warning': MagicMock(),
        'info': MagicMock(),
    }
    
    return patches


class MockStreamlitPage:
    """Base class for testing Streamlit pages."""
    
    def __init__(self):
        self.st_mock = MagicMock()
        self.session_state = {}
        
    def setup_mocks(self):
        """Setup common Streamlit mocks."""
        self.st_mock.session_state = self.session_state
        self.st_mock.text_input.return_value = ""
        self.st_mock.text_area.return_value = ""
        self.st_mock.button.return_value = False
        self.st_mock.checkbox.return_value = False
        
    def simulate_button_click(self, button_key: str):
        """Simulate a button click."""
        self.st_mock.button.return_value = True
        self.session_state[f"button_{button_key}"] = True
        
    def set_widget_value(self, key: str, value: Any):
        """Set a widget value in session state."""
        self.session_state[key] = value
