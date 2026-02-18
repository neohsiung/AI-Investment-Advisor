import streamlit as st
import os
from src.utils.google_auth import GoogleAuth

class AuthManager:
    """
    Manages Authentication state and login flow using Google OAuth.
    """
    def __init__(self):
        import json

        self.secret_path = os.getenv('GOOGLE_CLIENT_SECRET_PATH', 'client_secret.json')
        
        # v4.1.8: Robustness Fix for IsADirectoryError
        # 修正目錄衝突造成的 IsADirectoryError
        if os.path.isdir(self.secret_path):
            fallback_path = os.path.join('secrets', 'client_secret.json')
            if os.path.exists(fallback_path):
                self.secret_path = fallback_path
            else:
                fallback_path_2 = os.path.join(self.secret_path, 'client_secret.json')
                if os.path.exists(fallback_path_2):
                    self.secret_path = fallback_path_2

        self.cookie_name = "investment_advisor_auth"
        self.cookie_key = os.getenv('COOKIE_KEY', 'your_secret_cookie_key_should_be_long')
        self.redirect_uri = os.getenv('REDIRECT_URI', 'http://localhost:8501')

        # Determine if we have secret in Env variables (Cloud Run support)
        # Priority:
        # 1. GOOGLE_CLIENT_SECRET_JSON (StandardEnv content)
        # 2. client_secret.json (User's specific Env Var name)
        # 3. File at GOOGLE_CLIENT_SECRET_PATH (File mount)

        self.client_config = None

        # Try reading from Env Vars
        env_secret_content = os.getenv('GOOGLE_CLIENT_SECRET_JSON') or os.getenv('client_secret.json')

        if env_secret_content:
            try:
                self.client_config = json.loads(env_secret_content)
                # Ensure it's the right format (usually {"web": ...} or {"installed": ...})
            except json.JSONDecodeError:
                # Malformed JSON in env var
                print("Warning: Malformed JSON in env variable")
                pass

        # Final check: If no config and file doesn't exist/is directory, warn
        if not self.client_config and (not os.path.exists(self.secret_path) or os.path.isdir(self.secret_path)):
            print(f"Warning: Google Client Secret not found or invalid at {self.secret_path}")
            # We don't raise here to allow the app to boot, but login will fail later gracefully in GoogleAuth

        self.authenticator = GoogleAuth(
            secret_credentials_path=self.secret_path,
            redirect_uri=self.redirect_uri,
            cookie_key=self.cookie_key,
            cookie_name=self.cookie_name,
            client_config=self.client_config
        )

    def check_login(self):
        """
        Check if the user is authenticated.
        Returns: "AUTHENTICATED", "UNAUTHENTICATED", or "LOADING"
        """
        status = self.authenticator.check_authentification()
        # Fallback if check_authentification returns None (compatibility)
        if status is None:
             return "AUTHENTICATED" if st.session_state.get('connected') else "UNAUTHENTICATED"
        return status

    def login(self):
        """
        Renders the login button.
        """
        self.authenticator.login()

    def logout(self):
        """
        Logs out the user.
        """
        self.authenticator.logout()

    def get_current_user(self):
        """
        Returns a dict with user info: {'email': ..., 'name': ..., 'picture': ...}
        """
        if self.check_login():
            user_info = st.session_state.get('user_info', {})
            # Ensure email is present
            if 'email' not in user_info:
                # Fallback or strict error
                pass
            return user_info
        return None

# Singleton instance
auth_manager = AuthManager()
