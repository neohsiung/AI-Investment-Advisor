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
        This must be called at the start of the app.
        """
        self.authenticator.check_authentification()
        # The library stores state in st.session_state['connected']? 
        # Actually it's cleaner to check login status via the authenticator methods usually.
        # But looking at library source or common usage:
        return st.session_state.get('connected', False)
    
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
