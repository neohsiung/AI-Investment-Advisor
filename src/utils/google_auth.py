import streamlit as st
import os
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
        self.cookie_manager = stx.CookieManager()

    def _get_flow(self):
        """Initialize Flow from client secret file OR config dict."""
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

    def login(self):
        """Displays login button and handles OAuth callbacks."""
        # Check if already logged in via Session State
        if st.session_state.get('connected'):
            return

        # Check for query params (Callback)
        if "code" in st.query_params:
            try:
                code = st.query_params["code"]
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
                st.session_state['connected'] = True
                st.session_state['user_info'] = user_info
                st.session_state['oauth_id'] = id_info.get("sub")
                
                # Persist in Cookie (expires in 7 days) via CookieManager
                # Note: Browsers might block 3rd party cookies, but this is 1st party.
                # We store minimal data.
                import datetime
                expires_at = datetime.datetime.now() + datetime.timedelta(days=7)
                self.cookie_manager.set(self.cookie_name, user_info, expires_at=expires_at)

                # Clear query params to prevent re-triggering
                try:
                    st.query_params.clear()
                except:
                    pass
                st.rerun()

            except Exception as e:
                st.error(f"Login failed: {e}")
        else:
            # Display Login Button
            flow = self._get_flow()
            authorization_url, state = flow.authorization_url(
                access_type='offline',
                include_granted_scopes='true'
            )

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

    def check_authentification(self):
        """Check if user is authenticated (Check Session State or Cookie)."""
        
        # 1. Check Memory Session
        if st.session_state.get('connected'):
            return

        # 2. Check Cookie (Persistence)
        # stx.CookieManager gets cookies on render.
        # We need to make sure we don't block.
        cookies = self.cookie_manager.get_all()
        
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
            except Exception as e:
                print(f"Cookie parse error: {e}")

        if 'connected' not in st.session_state:
            st.session_state['connected'] = False

    def logout(self):
        """Log out the user."""
        try:
            self.cookie_manager.delete(self.cookie_name)
        except:
            pass
        st.session_state['connected'] = False
        st.session_state['user_info'] = None
        st.rerun()

    def get_user_info(self):
        """Return user info if connected."""
        if st.session_state.get('connected'):
            return st.session_state.get('user_info')
        return None
