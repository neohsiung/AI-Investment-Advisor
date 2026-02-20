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
            else:
                flow = google_auth_oauthlib.flow.Flow.from_client_secrets_file(
                    self.client_secret_path,
                    scopes=self.scopes
                )
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
                    # We already fetched tokens for this code, so just show the success screen
                    st.success("✅ **登入成功！請點擊按鈕進入系統 (Login successful! Click to enter)**")
                    
                    if st.button("🚀 進入系統 (Enter System)", type="primary", use_container_width=True):
                        try:
                            st.query_params.clear()
                        except Exception:
                            pass
                        st.rerun()
                    return

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

                # Store user info in session
                st.session_state['user_info'] = user_info
                st.session_state['oauth_id'] = id_info.get("sub")
                
                # Persist in Cookie (expires in 7 days) via CookieManager
                # Note: Browsers might block 3rd party cookies, but this is 1st party.
                # Store user info in cookie
                import datetime
                expires_at = datetime.datetime.now() + datetime.timedelta(days=7)
                self.cookie_manager.set(self.cookie_name, user_info, expires_at=expires_at)

                # Sync state immediately into session
                st.session_state['connected'] = True
                st.session_state['user_info'] = user_info
                if 'sub' in user_info:
                    st.session_state['oauth_id'] = user_info['sub']

                st.success("✅ **登入成功！請點擊按鈕進入系統 (Login successful! Click to enter)**")
                
                if st.button("🚀 進入系統 (Enter System)", type="primary", use_container_width=True):
                    # Clear query params internally on click
                    try:
                        st.query_params.clear()
                    except Exception:
                        pass
                    st.rerun()
                
                return # Crucial to abort execution so the frontend renders CookieManager iframe

            except Exception as e:
                if type(e).__name__ in ("RerunException", "RerunData", "StopException"):
                    raise  # Let Streamlit handle its internal control flow exceptions
                
                # Handle 'invalid_grant' - usually means reuse of Authorization Code
                # 處理 'invalid_grant' 錯誤 - 通常表示授權碼被重複使用
                st.error(f"Login failed: {e}")
                
                # Automatically clear invalid query params to allow retry
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
                   st.warning("⚠️ Authentication Unavailable")
                   st.info("The system is configured with a Service Account Key instead of an OAuth Client ID. Please see the Wiki for setup instructions.")
                else:
                    st.error(f"Configuration Error: {e}")

    def check_authentification(self):
        """Check if user is authenticated (Check Session State or Cookie)."""
        
        # 1. Check Memory Session
        if st.session_state.get('connected'):
            return

        # 2. Check Cookie (Persistence)
        # stx.CookieManager gets cookies on render.
        # We need to make sure we don't block.
        cookies = self.cookie_manager.get_all()
        
        # Retry logic for reading cookies (Essential for Cmd+Shift+R persistence)
        # stx.CookieManager is async and may return None initially.
        
        cookie_retry_count = st.session_state.get('auth_cookie_retries', 0)
        
        if cookies is None and cookie_retry_count < 3:
            # Increment retry counter
            st.session_state['auth_cookie_retries'] = cookie_retry_count + 1
            # CRITICAL FIX: Do NOT call st.rerun() here. 
            # We must return "LOADING" so auth_guard can call st.stop().
            # st.stop() flushes to the frontend, allowing the CookieManager iframe to mount.
            # Once mounted, the CookieManager will automatically send the cookie data back and trigger a rerun.
            return "LOADING"
        
        # Reset retries if we found cookies or gave up
        if cookies is not None:
             st.session_state['auth_cookie_retries'] = 0

        # If still None after retries, assume no cookies (or verify failed)
        if cookies is None:
             # Just in case, try one last check on None as empty dict
             cookies = {}

        if self.cookie_name in cookies:
            try:
                user_info = cookies[self.cookie_name]
                if user_info and 'email' in user_info:
                    st.session_state['connected'] = True
                    st.session_state['user_info'] = user_info
                    st.session_state['oauth_id'] = user_info.get('sub')
                    # Optional: Verify token if we stored the ID token, 
                    # but here we trust the cookie content for simplicity (assuming HTTPS/HttpOnly separation not fully possible in pure Streamlit app logic without backend middleware).
                    # For a low-risk internal tool, this JSON in cookie is acceptable.
                    st.rerun()
                    return "AUTHENTICATED"
            except Exception as e:
                print(f"Cookie parse error: {e}")

        if 'connected' not in st.session_state:
            st.session_state['connected'] = False
            
        return "UNAUTHENTICATED"

    def logout(self):
        """Log out the user."""
        try:
            self.cookie_manager.delete(self.cookie_name)
        except Exception:
            pass
        st.session_state['connected'] = False
        st.session_state['user_info'] = None
        st.rerun()

    def get_user_info(self):
        """Return user info if connected."""
        if st.session_state.get('connected'):
            return st.session_state.get('user_info')
        return None
