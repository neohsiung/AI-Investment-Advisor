
import pytest
from unittest.mock import MagicMock, patch
import sys

# Force clean state for these modules to ensure they pick up the mocks
# This must happen BEFORE any imports from src that rely on streamlit
for mod in ['src.auth', 'src.utils.google_auth', 'extra_streamlit_components', 'streamlit']:
    if mod in sys.modules:
        del sys.modules[mod]

# Mock streamlit globally
mock_st = MagicMock()
mock_st.session_state = {} # Initialize as dict so it persists writes
mock_st.query_params = {}
sys.modules["streamlit"] = mock_st

# Mock extra_streamlit_components globally
mock_stx = MagicMock()
sys.modules["extra_streamlit_components"] = mock_stx

# Now import the modules under test
import pandas as pd
from src.utils.google_auth import GoogleAuth
from src.repositories.transaction_repository import SqliteTransactionRepository
from src.repositories.settings_repository import SqliteSettingsRepository

# --- GoogleAuth Tests ---

@pytest.fixture
def mock_streamlit():
    """
    Returns the global mock since we injected it into sys.modules.
    Resets state between tests.
    """
    # Reset internal state
    mock_st.reset_mock()
    mock_st.session_state = {}
    mock_st.query_params = {}
    
    # Ensure methods are mocks
    mock_st.markdown = MagicMock()
    mock_st.rerun = MagicMock()
    mock_st.error = MagicMock()
    
    return mock_st

@pytest.fixture
def google_auth_instance():
    # Re-instantiate to ensure it uses the current global mocks
    return GoogleAuth("secret.json", "http://localhost:8501", "cookie_key")

def test_auth_login_display_button(mock_streamlit, google_auth_instance):
    # Case: Not connected, no code in params
    # Ensure session_state is empty
    mock_streamlit.session_state = {}
    mock_streamlit.query_params = {}

    with patch("google_auth_oauthlib.flow.Flow.from_client_secrets_file") as mock_flow_cls:
        mock_flow = MagicMock()
        mock_flow.authorization_url.return_value = ("http://auth_url", "state")
        mock_flow_cls.return_value = mock_flow

        google_auth_instance.login()

        # Should call markdown to display button
        mock_streamlit.markdown.assert_called()
        args, kwargs = mock_streamlit.markdown.call_args
        html_content = args[0]
        assert "http://auth_url" in html_content
        assert "Login with Google" in html_content

def test_auth_login_success(mock_streamlit, google_auth_instance):
    # Case: Code in params
    mock_streamlit.query_params = {"code": "auth_code"}

    with patch("google_auth_oauthlib.flow.Flow.from_client_secrets_file") as mock_flow_cls, \
         patch("google.oauth2.id_token.verify_oauth2_token") as mock_verify:

        mock_flow = MagicMock()
        mock_flow.credentials.id_token = "id_token"
        mock_flow.client_config = {'client_id': 'cid'}
        # Defensive return
        mock_flow.authorization_url.return_value = ("url", "state")
        mock_flow_cls.return_value = mock_flow

        # Verify token returns user info
        mock_verify.return_value = {
            "email": "test@example.com",
            "name": "Test User",
            "picture": "pic.jpg",
            "sub": "12345"
        }

        # Run login
        google_auth_instance.login()

        # Check for errors first
        if mock_streamlit.error.called:
             pytest.fail(f"st.error was called: {mock_streamlit.error.call_args}")

        # Assertions
        assert mock_streamlit.session_state.get('connected') is True
        assert mock_streamlit.session_state.get('user_info', {}).get('email') == "test@example.com"
        mock_streamlit.rerun.assert_called()

def test_auth_logout(mock_streamlit, google_auth_instance):
    mock_streamlit.session_state = {'connected': True, 'user_info': 'foo'}
    
    google_auth_instance.logout()
    
    # It should set connected to False
    assert mock_streamlit.session_state['connected'] is False
    assert mock_streamlit.session_state['user_info'] is None

def test_auth_check_authentication(mock_streamlit, google_auth_instance):
    # 1. Test init if missing
    mock_streamlit.session_state = {}
    google_auth_instance.check_authentification()
    assert 'connected' in mock_streamlit.session_state
    assert mock_streamlit.session_state['connected'] is False

    # 2. Test restore from cookie
    mock_streamlit.session_state = {} # Clear
    
    # Mock CookieManager get_all
    # GoogleAuth.cookie_manager is a Mock (from mock_stx.CookieManager())
    # We need to access the specific instance used by google_auth_instance
    
    # Since we can't easily reach the inner mock instance created inside __init__,
    # we can try to patch the method on the class or rely on the fact that mock_stx returns a mock
    # which returns a mock.
    
    # Better: Inspect the instance's cookie_manager attribute
    google_auth_instance.cookie_manager.get_all.return_value = {
        "investment_advisor_auth": {
            "email": "cookie@example.com",
            "sub": "cookie_sub"
        }
    }
    google_auth_instance.cookie_name = "investment_advisor_auth"
    
    google_auth_instance.check_authentification()
    
    assert mock_streamlit.session_state['connected'] is True
    assert mock_streamlit.session_state['user_info']['email'] == "cookie@example.com"


# --- TransactionRepository Tests (Unchanged) ---

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

# --- SettingsRepository Tests (Unchanged) ---
@pytest.fixture
def mock_db_conn_settings():
    with patch("src.repositories.settings_repository.get_db_connection") as mock_conn:
        yield mock_conn

def test_settings_repo_get_all(mock_db_conn_settings):
    repo = SqliteSettingsRepository()
    mock_result = MagicMock()
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
