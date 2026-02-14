import sys
from unittest.mock import MagicMock
import pytest

# Centralized Mocking to prevent decorator pollution and Protobuf conflicts
def pytest_configure(config):
    # This runs before any tests are collected or imported
    
    # Mock Streamlit
    if "streamlit" not in sys.modules:
        mock_st = MagicMock()
        def mock_cache_data(*args, **kwargs):
            def decorator(func):
                return func
            return decorator
        mock_cache_data.clear = MagicMock()
        mock_st.cache_data = mock_cache_data
        
        # Mock columns to handle spec variations
        def mock_columns(spec):
            if isinstance(spec, int):
                return [MagicMock() for _ in range(spec)]
            elif isinstance(spec, (list, tuple)):
                return [MagicMock() for _ in range(len(spec))]
            return [MagicMock()]
        mock_st.columns.side_effect = mock_columns
        
        sys.modules["streamlit"] = mock_st
    else:
        # If already imported (e.g. by another mock or early import), patch it
        mock_st = sys.modules["streamlit"]
        if not hasattr(mock_st.cache_data, 'clear'):
            def mock_cache_data(*args, **kwargs):
                def decorator(func):
                    return func
                return decorator
            mock_cache_data.clear = MagicMock()
            mock_st.cache_data = mock_cache_data

    # Mock other problematic modules
    problematic_modules = [
        "extra_streamlit_components",
        "plotly.express",
        "streamlit.components.v1",
        "streamlit.components.v1.components"
    ]
    for mod in problematic_modules:
        if mod not in sys.modules:
            sys.modules[mod] = MagicMock()

@pytest.fixture
def mock_streamlit_module():
    """Fixture to provide access to the centralized Streamlit mock."""
    return sys.modules.get("streamlit")
