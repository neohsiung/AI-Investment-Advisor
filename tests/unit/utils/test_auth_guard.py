import pytest
from unittest.mock import patch, MagicMock
import streamlit as st
from src.utils.auth_guard import require_authentication

@pytest.fixture
def mock_auth():
    with patch("src.utils.auth_guard.auth_manager") as mock_mgr, \
         patch("src.repositories.user_repository.AlchemyUserRepository") as mock_repo, \
         patch("src.services.settings_service.SettingsService") as mock_settings, \
         patch("src.services.llm_onboarding_service.LLMOnboardingService") as mock_onboard:
        yield mock_mgr, mock_repo, mock_settings, mock_onboard

def test_require_authentication_loading(mock_auth):
    mock_mgr = mock_auth[0]
    mock_mgr.check_login.return_value = "LOADING"
    
    with patch("streamlit.info"), patch("streamlit.stop") as mock_stop:
        mock_stop.side_effect = Exception("st.stop")
        with pytest.raises(Exception, match="st.stop"):
            require_authentication()
        mock_stop.assert_called_once()

def test_require_authentication_unauthenticated(mock_auth):
    mock_mgr = mock_auth[0]
    mock_mgr.check_login.return_value = "UNAUTHENTICATED"
    
    with patch("streamlit.warning"), patch("streamlit.stop") as mock_stop:
        mock_stop.side_effect = Exception("st.stop")
        with pytest.raises(Exception, match="st.stop"):
            require_authentication()
        mock_mgr.login.assert_called_once()
        mock_stop.assert_called_once()

def test_require_authentication_authenticated_existing_user(mock_auth):
    mock_mgr, mock_repo, mock_settings, mock_onboard = mock_auth
    mock_mgr.check_login.return_value = "AUTHENTICATED"
    mock_mgr.get_current_user.return_value = {"email": "test@example.com", "name": "Test User"}
    
    mock_repo.return_value.get_by_identity.return_value = {"id": "user-uuid-123", "email": "test@example.com"}
    mock_settings.return_value.get_setting.return_value = "sk_existing_key"
    
    user = require_authentication()
    assert user["id"] == "user-uuid-123"
    assert user["email"] == "test@example.com"

def test_require_authentication_authenticated_new_user(mock_auth):
    mock_mgr, mock_repo, mock_settings, mock_onboard = mock_auth
    mock_mgr.check_login.return_value = "AUTHENTICATED"
    mock_mgr.get_current_user.return_value = {"email": "new@example.com", "name": "New User"}
    
    # User not found in DB
    mock_repo.return_value.get_by_identity.return_value = None
    mock_repo.return_value.create_user.return_value = "new-uuid-456"
    
    user = require_authentication()
    assert user["id"] == "new-uuid-456"
    # Should have called create_user
    mock_repo.return_value.create_user.assert_called_once_with("new@example.com", name="New User")
    # Should have saved a webhook api key
    mock_settings.return_value.save_setting.assert_called()

def test_require_authentication_invalid_data(mock_auth):
    mock_mgr = mock_auth[0]
    mock_mgr.check_login.return_value = "AUTHENTICATED"
    mock_mgr.get_current_user.return_value = {} # Missing email
    
    with patch("streamlit.error"), patch("streamlit.stop") as mock_stop:
        mock_stop.side_effect = Exception("st.stop")
        with pytest.raises(Exception, match="st.stop"):
            require_authentication()
        mock_mgr.logout.assert_called_once()
        mock_stop.assert_called_once()
