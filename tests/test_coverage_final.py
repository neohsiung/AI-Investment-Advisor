
import pytest
from unittest.mock import MagicMock, patch
import pandas as pd
from src.utils.google_auth import GoogleAuth
from src.repositories.transaction_repository import SqliteTransactionRepository
from src.repositories.settings_repository import SqliteSettingsRepository

# --- GoogleAuth Tests ---

@pytest.fixture
def mock_streamlit():
    with patch("src.utils.google_auth.st") as mock_st:
        # Defaults
        mock_st.session_state = {}
        mock_st.query_params = {}
        yield mock_st

@pytest.fixture
def google_auth_instance():
    return GoogleAuth("secret.json", "http://localhost:8501", "cookie_key")

def test_auth_login_display_button(mock_streamlit, google_auth_instance):
    # Case: Not connected, no code in params
    with patch("google_auth_oauthlib.flow.Flow.from_client_secrets_file") as mock_flow_cls:
        mock_flow = MagicMock()
        mock_flow.authorization_url.return_value = ("http://auth_url", "state")
        mock_flow_cls.return_value = mock_flow
        
        google_auth_instance.login()
        
        mock_streamlit.link_button.assert_called_with("Login with Google", "http://auth_url", type="primary")

def test_auth_login_success(mock_streamlit, google_auth_instance):
    # Case: Code in params
    mock_streamlit.query_params = {"code": "auth_code"}
    
    with patch("google_auth_oauthlib.flow.Flow.from_client_secrets_file") as mock_flow_cls, \
         patch("google.oauth2.id_token.verify_oauth2_token") as mock_verify:
        
        mock_flow = MagicMock()
        mock_flow.credentials.id_token = "id_token"
        mock_flow.client_config = {'client_id': 'cid'}
        mock_flow_cls.return_value = mock_flow
        
        mock_verify.return_value = {
            "email": "test@example.com",
            "name": "Test User",
            "picture": "pic.jpg",
            "sub": "12345"
        }
        
        google_auth_instance.login()
        
        assert mock_streamlit.session_state['connected'] is True
        assert mock_streamlit.session_state['user_info']['email'] == "test@example.com"
        mock_streamlit.rerun.assert_called()

def test_auth_logout(mock_streamlit, google_auth_instance):
    mock_streamlit.session_state['connected'] = True
    google_auth_instance.logout()
    assert mock_streamlit.session_state['connected'] is False

def test_auth_check_authentication(mock_streamlit, google_auth_instance):
    # Should init session state if missing
    google_auth_instance.check_authentification()
    assert 'connected' in mock_streamlit.session_state
    
    
# --- TransactionRepository Tests ---

@pytest.fixture
def mock_db_conn():
    with patch("src.repositories.transaction_repository.get_db_connection") as mock_conn:
        yield mock_conn

def test_repo_delete(mock_db_conn):
    repo = SqliteTransactionRepository()
    repo.delete("user123", "trans123")
    
    mock_db_conn.return_value.__enter__.return_value.execute.assert_called()

def test_repo_get_all_by_user_df(mock_db_conn):
    repo = SqliteTransactionRepository()
    
    # Mock dataframe return for get_all_by_user_df
    mock_df = pd.DataFrame({
        'ticker': ['AAPL', 'AAPL', 'GOOG'],
        'action': ['BUY', 'SELL', 'BUY'],
        'quantity': [10, 5, 5],
        'price': [100, 110, 200],
        'fees': [1, 1, 1],
        'amount': [1000, 550, 1000]
    })
    
    with patch("pandas.read_sql", return_value=mock_df):
        df = repo.get_all_by_user_df("user1")
        assert not df.empty
        assert len(df) == 3

# --- SettingsRepository Tests ---
@pytest.fixture
def mock_db_conn_settings():
    with patch("src.repositories.settings_repository.get_db_connection") as mock_conn:
        yield mock_conn

def test_settings_repo_get_all(mock_db_conn_settings):
    repo = SqliteSettingsRepository()
    
    mock_result = MagicMock()
    # fetchall returns list of tuples/rows
    mock_result.fetchall.return_value = [
        ('theme', 'dark'), ('notifications', 'true')
    ]
    mock_db_conn_settings.return_value.__enter__.return_value.execute.return_value = mock_result
    
    settings_list = repo.get_all("user1")
    settings = dict(settings_list)
    assert settings['theme'] == 'dark'
    assert settings['notifications'] == 'true'

def test_settings_repo_set(mock_db_conn_settings):
    repo = SqliteSettingsRepository()
    repo.set("user1", "theme", "light")
    mock_db_conn_settings.return_value.__enter__.return_value.execute.assert_called()
