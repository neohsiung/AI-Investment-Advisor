import pytest
from unittest.mock import MagicMock, patch
import sys

# Streamlit is centrally mocked in conftest.py
sys.modules["extra_streamlit_components"] = MagicMock()
sys.modules["google_auth_oauthlib"] = MagicMock()
sys.modules["google_auth_oauthlib.flow"] = MagicMock()
sys.modules["google.oauth2"] = MagicMock()
sys.modules["google.auth.transport"] = MagicMock()

from src.utils.auth_guard import require_authentication


class TestAuthGuard:
    
    @patch('src.repositories.user_repository.AlchemyUserRepository')
    @patch('src.utils.auth_guard.auth_manager')
    @patch('src.utils.auth_guard.st')
    def test_require_authentication_loading(self, mock_st, mock_auth, mock_user_repo):
        """Test LOADING status stops execution with info message"""
        mock_auth.check_login.return_value = "LOADING"
        
        require_authentication()
        
        mock_st.info.assert_called_with("🔄 驗證中... (Authenticating...)", icon="🔄")
        mock_st.stop.assert_called()

    @patch('src.repositories.user_repository.AlchemyUserRepository')
    @patch('src.utils.auth_guard.auth_manager')
    @patch('src.utils.auth_guard.st')
    def test_require_authentication_unauthenticated(self, mock_st, mock_auth, mock_user_repo):
        """Test UNAUTHENTICATED status stops execution with warning"""
        mock_auth.check_login.return_value = "UNAUTHENTICATED"
        
        require_authentication()
        
        mock_st.warning.assert_called_with("⚠️ 請先登入 (Please login first)")
        mock_st.stop.assert_called()

    @patch('src.repositories.user_repository.AlchemyUserRepository')
    @patch('src.utils.auth_guard.auth_manager')
    @patch('src.utils.auth_guard.st')
    def test_require_authentication_false(self, mock_st, mock_auth, mock_user_repo):
        """Test False (legacy boolean) stops execution"""
        mock_auth.check_login.return_value = False
        
        require_authentication()
        
        mock_st.warning.assert_called_with("⚠️ 請先登入 (Please login first)")
        mock_st.stop.assert_called()

    @patch('src.repositories.user_repository.AlchemyUserRepository')
    @patch('src.utils.auth_guard.auth_manager')
    @patch('src.utils.auth_guard.st')
    def test_require_authentication_authenticated_success(self, mock_st, mock_auth, mock_user_repo):
        """Test AUTHENTICATED returns user object"""
        mock_auth.check_login.return_value = "AUTHENTICATED"
        mock_auth.get_current_user.return_value = {'email': 'test@example.com', 'name': 'Test User'}
        
        # Mock user repo return
        mock_repo_inst = mock_user_repo.return_value
        mock_repo_inst.get_by_identity.return_value = {'id': 'uuid-123', 'email': 'test@example.com'}
        
        user = require_authentication()
        
        assert user['email'] == 'test@example.com'
        assert user['name'] == 'Test User'
        assert user['id'] == 'uuid-123'
        mock_st.stop.assert_not_called()

    @patch('src.repositories.user_repository.AlchemyUserRepository')
    @patch('src.utils.auth_guard.auth_manager')
    @patch('src.utils.auth_guard.st')
    def test_require_authentication_invalid_user_data(self, mock_st, mock_auth, mock_user_repo):
        """Test invalid user data triggers logout and stop"""
        mock_auth.check_login.return_value = "AUTHENTICATED"
        mock_auth.get_current_user.return_value = {'name': 'Test'}  # Missing email
        
        require_authentication()
        
        mock_st.error.assert_called()
        mock_auth.logout.assert_called()
        mock_st.stop.assert_called()
