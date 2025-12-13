import streamlit as st
import os
import google_auth_oauthlib.flow
from google.oauth2 import id_token
from google.auth.transport import requests
import json
import base64

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
        # Note: st.query_params is the new API, st.experimental_get_query_params is deprecated
        # but for Py 3.8 / older streamlit versions, we might need to check version.
        # Assuming reasonably new streamlit.
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

                # Store user info in session
                st.session_state['connected'] = True
                st.session_state['user_info'] = {
                    "email": id_info.get("email"),
                    "name": id_info.get("name"),
                    "picture": id_info.get("picture")
                }
                st.session_state['oauth_id'] = id_info.get("sub")

                # Clear query params to prevent re-triggering
                # st.query_params.clear() # This might not be enough to clear URL bar visually
                st.rerun()

            except Exception as e:
                st.error(f"Login failed: {e}")
                # Optional: Clear params manually if needed
        else:
            # Display Login Button
            flow = self._get_flow()
            authorization_url, state = flow.authorization_url(
                access_type='offline',
                include_granted_scopes='true'
            )

            st.link_button("Login with Google", authorization_url, type="primary")

    def check_authentification(self):
        """Check if user is authenticated (Check Session State)."""
        # In a real persistence scenario, we would check cookies here.
        # For simplicity and Streamlit Cloud compatibility without extra components,
        # we rely on Session State.
        # (Implementing secure JWT cookies in pure Streamlit requires extra component or hacky headers)

        # Simplified for v1.1.0: Session State only (Lost on refresh)
        if 'connected' not in st.session_state:
            st.session_state['connected'] = False

    def logout(self):
        """Log out the user."""
        st.session_state['connected'] = False
        st.session_state['user_info'] = None
        st.rerun()

    def get_user_info(self):
        """Return user info if connected."""
        if st.session_state.get('connected'):
            return st.session_state.get('user_info')
        return None
