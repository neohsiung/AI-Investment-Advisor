import pytest
from unittest.mock import MagicMock, patch
import sys
import os
import importlib

# Ensure src.auth uses the mocked streamlit from sys.modules
from src import auth

class TestAuthManager:
    
    @pytest.fixture
    def auth_manager(self, mock_streamlit_module):
        mod_name = 'src.auth'
        if mod_name in sys.modules:
            auth_mod = importlib.reload(sys.modules[mod_name])
        else:
            auth_mod = importlib.import_module(mod_name)
            
        # Mock GoogleAuth within src.auth scope
        with patch('src.auth.GoogleAuth') as mock_ga:
            with patch.dict(os.environ, {'GOOGLE_CLIENT_SECRET_JSON': '{"web": {}}'}):
                manager = auth_mod.AuthManager()
                yield manager, mock_ga

    def test_init(self, auth_manager):
        """Test initialization of AuthManager."""
        manager, mock_ga = auth_manager
        mock_ga.assert_called()
        assert manager.client_config == {"web": {}}

    def test_check_login_delegates(self, auth_manager):
        """Test that check_login delegates to authenticator"""
        manager, mock_ga = auth_manager
        
        # Case 1: LOADING
        manager.authenticator.check_authentification.return_value = "LOADING"
        assert manager.check_login() == "LOADING"
        
        # Case 2: AUTHENTICATED
        manager.authenticator.check_authentification.return_value = "AUTHENTICATED"
        assert manager.check_login() == "AUTHENTICATED"

        # Case 3: None (Legacy fallback)
        manager.authenticator.check_authentification.return_value = None
        st_mock = sys.modules["streamlit"]
        
        st_mock.session_state = {'connected': False}
        assert manager.check_login() == "UNAUTHENTICATED"
             
        st_mock.session_state = {'connected': True}
        assert manager.check_login() == "AUTHENTICATED"

    def test_get_current_user(self, auth_manager):
        """Test get_current_user logic."""
        manager, _ = auth_manager
        st_mock = sys.modules["streamlit"]
        
        # Setup session state
        st_mock.session_state = {'connected': True, 'user_info': {'email': 'test@test.com'}}
        
        # Ensure authenticator reports as authenticated
        manager.authenticator.check_authentification.return_value = "AUTHENTICATED"
        
        # We need to mock how get_current_user accesses session_state
        # src.auth imports st. If we reloaded auth, it uses mock_st.
        
        user = manager.get_current_user()
        assert user['email'] == 'test@test.com'

    def test_login_logout(self, auth_manager):
        """Test login and logout delegation."""
        manager, mock_ga = auth_manager
    
        manager.login()
        # authenticator is the instance returned by mock_ga
        # manager.authenticator IS mock_ga.return_value
        
        manager.authenticator.login.assert_called()
        
        manager.logout()
        manager.authenticator.logout.assert_called()
