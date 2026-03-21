import pytest
from unittest.mock import MagicMock, patch
import sys
import importlib

# DO NOT mock sys.modules globally here. Use fixture.

from src.utils import google_auth

class TestGoogleAuthUnit:
    
    @pytest.fixture
    def mock_streamlit_module(self, monkeypatch):
        """Fixture to mock streamlit and related Google auth modules in sys.modules."""
        mock_st = MagicMock()
        mock_extra_st_components = MagicMock()
        mock_google_auth_oauthlib_flow = MagicMock()
        mock_google_auth_oauthlib = MagicMock()
        mock_google_oauth2 = MagicMock()
        mock_google_auth_transport = MagicMock()

        monkeypatch.setitem(sys.modules, "streamlit", mock_st)
        monkeypatch.setitem(sys.modules, "extra_streamlit_components", mock_extra_st_components)
        monkeypatch.setitem(sys.modules, "google_auth_oauthlib.flow", mock_google_auth_oauthlib_flow)
        monkeypatch.setitem(sys.modules, "google_auth_oauthlib", mock_google_auth_oauthlib)
        # CRITICAL: Link the submodule to the parent package so attribute access works
        mock_google_auth_oauthlib.flow = mock_google_auth_oauthlib_flow
        
        monkeypatch.setitem(sys.modules, "google.oauth2", mock_google_oauth2)
        monkeypatch.setitem(sys.modules, "google.auth.transport", mock_google_auth_transport)
        
        # Patch os.path.exists for the credentials file
        def mock_exists(path):
            if "client_secret.json" in str(path):
                return True
            return os.path.exists(path)
        monkeypatch.setattr("os.path.exists", mock_exists)
        
        # Yield the mock_st object for direct access in tests if needed
        yield mock_st

    @pytest.fixture
    def auth_instance(self, mock_streamlit_module):
        # We need to ensure google_auth uses our mocked streamlit
        mod_name = 'src.utils.google_auth'
        if mod_name in sys.modules:
             return importlib.reload(sys.modules[mod_name]).GoogleAuth(
                secret_credentials_path='client_secret.json',
                redirect_uri='http://localhost:8501',
                cookie_key='test_secret_key'
             )
        else:
             mod = importlib.import_module(mod_name)
             return mod.GoogleAuth(
                secret_credentials_path='client_secret.json',
                redirect_uri='http://localhost:8501',
                cookie_key='test_secret_key'
             )


    def test_check_authentification_returns_loading(self, auth_instance):
        """Test that check_authentification returns 'LOADING' when cookies syncing."""
        st_mock = sys.modules["streamlit"]
        st_mock.session_state = {'auth_cookie_retries': 0}
        st_mock.rerun = MagicMock()
        
        # Configure cookie manager
        auth_instance.cookie_manager.get_all.return_value = None
        
        status = auth_instance.check_authentification()
        assert status == "LOADING"

    def test_check_authentification_returns_unauthenticated(self, auth_instance):
        """Test final UNAUTHENTICATED state"""
        st_mock = sys.modules["streamlit"]
        st_mock.session_state = {'auth_cookie_retries': 3}
        
        auth_instance.cookie_manager.get_all.return_value = {}
             
        status = auth_instance.check_authentification()
        assert status == "UNAUTHENTICATED"
