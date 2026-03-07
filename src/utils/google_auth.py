import streamlit as st
import os
# Allow basic HTTP for OAuth flow (Localhost support)
# 允許本地開發使用 HTTP 進行 OAuth 驗證
os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'

import google_auth_oauthlib.flow
from google.oauth2 import id_token
from google.auth.transport import requests
import json
import base64
import extra_streamlit_components as stx
import time

class GoogleAuth:
    def __init__(self, secret_credentials_path, redirect_uri, cookie_key, cookie_name="investment_advisor_auth", client_config=None):
        self.client_secret_path = secret_credentials_path
        self.client_config = client_config
        self.redirect_uri = redirect_uri
        self.cookie_name = cookie_name
        self.cookie_key = cookie_key
        # Scopes required for OpenID Connect
        self.scopes = [
            "openid",
            "https://www.googleapis.com/auth/userinfo.email",
            "https://www.googleapis.com/auth/userinfo.profile"
        ]
        self._cookie_manager = None
    
    @property
    def cookie_manager(self):
        if self._cookie_manager is None:
            import extra_streamlit_components as stx
            # A strict key is REQUIRED for stx.CookieManager to preserve its identity across component remounts!
            self._cookie_manager = stx.CookieManager(key="auth_cookie_manager_stable")
        return self._cookie_manager

    def _get_flow(self):
        """Initialize Flow from client secret file OR config dict."""
        try:
            if self.client_config:
                flow = google_auth_oauthlib.flow.Flow.from_client_config(
                    self.client_config,
                    scopes=self.scopes
                )
            elif self.client_secret_path and os.path.exists(self.client_secret_path):
                flow = google_auth_oauthlib.flow.Flow.from_client_secrets_file(
                    self.client_secret_path,
                    scopes=self.scopes
                )
            else:
                # v4.2.3: Graceful failure when no credentials found
                raise ValueError("MISSING_CREDENTIALS")
            
            flow.redirect_uri = self.redirect_uri
            return flow
        except ValueError as e:
            # Catch specific error 'Client secrets must be for a web or installed app'
            if "Client secrets must be for a web or installed app" in str(e):
                # Raise as a clean error for the caller (dashboard) to handle UI for
                raise ValueError("WRONG_CREDENTIAL_TYPE")
            else:
                raise e

    def login(self):
        """Displays login button and handles OAuth callbacks."""
        # Check if already logged in via Session State
        if st.session_state.get('connected'):
            return

        # Check for query params (Callback)
        if "code" in st.query_params:
            try:
                code = st.query_params["code"]
                
                # Prevent Double Execution (Fix invalid_grant)
                if st.session_state.get("last_used_code") == code:
                    # Only show success screen if we ACTUALLY have the user info
                    if st.session_state.get('user_info'):
                        # We already fetched tokens for this code, so just show the success screen
                        st.success("✅ **登入成功！請點擊按鈕進入系統 (Login successful! Click to enter)**")
                        
                        if st.button("🚀 進入系統 (Enter System)", type="primary", use_container_width=True):
                            st.session_state['connected'] = True
                            try:
                                st.query_params.clear()
                            except Exception as e:
                                pass
                            st.rerun()
                        return
                    else:
                        # Corrupted state: code exists, but user_info is gone (e.g., from an error logout).
                        # Since OAuth codes are single-use, we CANNOT fetch again. 
                        # We must clear the URL parameters and force a fresh login attempt.
                        if "last_used_code" in st.session_state:
                            del st.session_state["last_used_code"]
                        try:
                            st.query_params.clear()
                        except Exception:
                            pass
                        st.rerun()

                st.session_state["last_used_code"] = code

                flow = self._get_flow()
                flow.fetch_token(code=code)
                credentials = flow.credentials

                # Verify ID Token
                token_request = requests.Request()
                id_info = id_token.verify_oauth2_token(
                    credentials.id_token, token_request, flow.client_config['client_id'], clock_skew_in_seconds=60
                )

                user_info = {
                    "email": id_info.get("email"),
                    "name": id_info.get("name"),
                    "picture": id_info.get("picture"),
                    "sub": id_info.get("sub")
                }

                # Store user info in session IMMEDIATELY
                st.session_state['user_info'] = user_info
                st.session_state['oauth_id'] = id_info.get("sub")
                st.session_state['connected'] = True
                
                # Persist in Cookie (expires in 7 days) via CookieManager
                import datetime
                expires_at = datetime.datetime.now() + datetime.timedelta(days=7)
                self.cookie_manager.set(self.cookie_name, user_info, expires_at=expires_at)

                # Clear query params so refresh doesn't trigger invalid_grant
                try:
                    st.query_params.clear()
                except Exception:
                    pass

                st.success("✅ **登入成功！正在進入系統... (Login successful! Entering system...)**")
                
                # Use a small sleep to ensure the frontend receives the CookieManager iframe
                time.sleep(1.0)
                st.rerun()

            except Exception as e:
                if type(e).__name__ in ("RerunException", "RerunData", "StopException"):
                    raise  # Let Streamlit handle its internal control flow exceptions
                
                error_str = str(e)
                if "invalid_grant" in error_str.lower():
                    # Handle 'invalid_grant' - usually means reuse of Authorization Code (e.g. F5 refresh on callback page)
                    # 處理 'invalid_grant' 錯誤 - 默默清空過期授權碼並重整，不要顯示嚇人的錯誤
                    try:
                        st.query_params.clear()
                    except Exception:
                        pass
                    st.rerun()
                else:
                    st.error(f"Login failed: {error_str}")
                    try:
                        st.query_params.clear()
                        time.sleep(1) 
                        st.rerun()
                    except Exception:
                        pass
        else:
            # Display Login Button
            try:
                flow = self._get_flow()
                authorization_url, state = flow.authorization_url(
                    access_type='offline',
                    include_granted_scopes='true'
                )
                
                # Render Clean Login Button
                st.markdown(
                    f"""
                    <a href="{authorization_url}" target="_self" style="
                        display: inline-block;
                        padding: 0.5rem 1rem;
                        color: white;
                        background-color: #6366f1;
                        border-radius: 0.375rem;
                        text-decoration: none;
                        font-weight: 500;
                        text-align: center;
                    ">
                        Login with Google
                    </a>
                    """,
                    unsafe_allow_html=True
                )
            except ValueError as e:
                if str(e) == "WRONG_CREDENTIAL_TYPE":
                   st.warning("⚠️ Authentication Unavailable (Wrong Type)")
                   st.info("The system is configured with a Service Account Key instead of an OAuth Client ID. Please see the Wiki for setup instructions.")
                elif str(e) == "MISSING_CREDENTIALS":
                   st.warning("⚠️ Authentication Unavailable (Missing Secrets)")
                   st.info("No Google Client Secrets found (neither client_secret.json nor environment variables). Restricted mode enabled.")
                else:
                    st.error(f"Configuration Error: {e}")

    def check_authentification(self):
        """Check if user is authenticated (Check Session State or Cookie)."""
        
        # 1. Check Memory Session
        if st.session_state.get('connected'):
            print("[DEBUG AUTH] check_authentification: Found 'connected' in session_state -> AUTHENTICATED")
            return "AUTHENTICATED"

        # 2. Check Cookie (Persistence)
        cookies = self.cookie_manager.get_all()
        print(f"[DEBUG AUTH] check_authentification: Retrieved cookies from manager: {cookies}")
        
        cookie_retry_count = st.session_state.get('auth_cookie_retries', 0)
        
        if cookies is None and cookie_retry_count < 3:
            st.session_state['auth_cookie_retries'] = cookie_retry_count + 1
            print(f"[DEBUG AUTH] check_authentification: Cookies is None. Incrementing retry to {cookie_retry_count + 1}. Returning LOADING.")
            return "LOADING"
        
        if cookies is not None:
             st.session_state['auth_cookie_retries'] = 0
             print("[DEBUG AUTH] check_authentification: Cookies NOT None. Resetting retries.")

        if cookies is None:
             print("[DEBUG AUTH] check_authentification: Cookies completely missing/None after retries. Defaulting to empty dict.")
             cookies = {}

        if self.cookie_name in cookies:
            try:
                user_info = cookies[self.cookie_name]
                print(f"[DEBUG AUTH] Found cookie '{self.cookie_name}': {user_info}")
                if user_info and 'email' in user_info:
                    st.session_state['connected'] = True
                    st.session_state['user_info'] = user_info
                    st.session_state['oauth_id'] = user_info.get('sub')
                    print("[DEBUG AUTH] Cookie verified and applied. Returning AUTHENTICATED.")
                    return "AUTHENTICATED"
                else:
                    print(f"[DEBUG AUTH] Cookie found but missing 'email' or empty: {user_info}")
            except Exception as e:
                print(f"[DEBUG AUTH] Cookie parse error: {e}")

        if 'connected' not in st.session_state:
            st.session_state['connected'] = False
            
        return "UNAUTHENTICATED"

    def logout(self):
        """Log out the user."""
        try:
            self.cookie_manager.delete(self.cookie_name)
        except Exception as e:
            pass
        st.session_state['connected'] = False
        st.session_state['user_info'] = None
        if 'oauth_id' in st.session_state:
            st.session_state['oauth_id'] = None
        if 'last_used_code' in st.session_state:
            del st.session_state['last_used_code']
        st.rerun()

    def get_user_info(self):
        """Return user info if connected."""
        if st.session_state.get('connected'):
            return st.session_state.get('user_info')
        return None
