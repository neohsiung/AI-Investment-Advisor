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
        monkeypatch.setitem(sys.modules, "google.oauth2", mock_google_oauth2)
        monkeypatch.setitem(sys.modules, "google.auth.transport", mock_google_auth_transport)
        
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


    def test_get_flow_raises_value_error_on_wrong_credential_type(self, auth_instance):
        """Test that _get_flow raises ValueError instead of st.stop when credential type is wrong."""
        with patch('google_auth_oauthlib.flow.Flow.from_client_secrets_file') as mock_flow:
            # Simulate the specific ValueError raised by google library
            mock_flow.side_effect = ValueError("Client secrets must be for a web or installed app")
            
            with pytest.raises(ValueError) as excinfo:
                auth_instance._get_flow()
            
            assert str(excinfo.value) == "WRONG_CREDENTIAL_TYPE"

    def test_get_flow_raises_other_value_errors(self, auth_instance):
        """Test that _get_flow re-raises other ValueErrors."""
        with patch('google_auth_oauthlib.flow.Flow.from_client_secrets_file') as mock_flow:
            mock_flow.side_effect = ValueError("Some other error")
            
            with pytest.raises(ValueError) as excinfo:
                auth_instance._get_flow()
            
            assert str(excinfo.value) == "Some other error"

    def test_login_handles_wrong_credential_type(self, auth_instance):
        """Test that login() catches WRONG_CREDENTIAL_TYPE and shows warning instead of crashing."""
        with patch.object(auth_instance, '_get_flow') as mock_get_flow:
            mock_get_flow.side_effect = ValueError("WRONG_CREDENTIAL_TYPE")
            
            # Setup clean mocks
            st_mock = sys.modules["streamlit"]
            st_mock.reset_mock()
            st_mock.session_state = {}
            st_mock.query_params = {}
            
            auth_instance.login()
            
            # Should have called st.warning
            st_mock.warning.assert_called_with("⚠️ Authentication Unavailable")
            # Should NOT have called st.stop() or st.error() in the old crashing way
            st_mock.stop.assert_not_called()

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
