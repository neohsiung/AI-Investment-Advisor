import streamlit as st
import os
# Allow basic HTTP for OAuth flow (Localhost support)
# 允許本地開發使用 HTTP 進行 OAuth 驗證
os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'

import google_auth_oauthlib.flow
from google.auth.transport import requests
import json
import base64
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
        # Isolate CookieManager per user session instead of globally
        # to prevent thread-safety issues and cross-session leaks
        if "auth_cookie_manager" not in st.session_state:
            import extra_streamlit_components as stx
            st.session_state["auth_cookie_manager"] = stx.CookieManager(key="auth_cookie_manager_stable")
        return st.session_state["auth_cookie_manager"]

    def login(self):
        """
        Redirects the user to the FastAPI Auth Hub.
        The backend handles the Google OAuth flow and redirects back here with a cookie.
        """
        # Point to the FastAPI backend (port 8000)
        backend_login_url = "http://localhost:8000/api/auth/login"
        
        # Display a clean login page
        st.markdown("""
            <div style="text-align: center; margin-top: 50px;">
                <h2 style='color: #4f46e5;'>🚀 AI Investment Advisor</h2>
                <p style='color: #6b7280;'>Sign in to access your professional investment suite</p>
            </div>
        """, unsafe_allow_html=True)
        
        # Use a standard <a> tag styled as a button. 
        # This bypasses iframe 'allow-top-navigation' sandbox issues.
        st.markdown(f"""
            <div style="text-align: center; margin-top: 30px;">
                <a href="{backend_login_url}" target="_self" style="
                    background-color: #4285F4;
                    color: white;
                    padding: 14px 40px;
                    border: none;
                    border-radius: 6px;
                    font-size: 18px;
                    font-weight: 600;
                    text-decoration: none;
                    display: inline-block;
                    box-shadow: 0 4px 10px rgba(0,0,0,0.15);
                    transition: transform 0.2s, background-color 0.2s;
                " onmouseover="this.style.backgroundColor='#357abd'; this.style.transform='scale(1.02)'" 
                   onmouseout="this.style.backgroundColor='#4285F4'; this.style.transform='scale(1)'">
                    Continue with Google
                </a>
            </div>
        """, unsafe_allow_html=True)
        st.stop()

    def check_authentification(self):
        """Check if user is authenticated (Check Session State or Cookie)."""
        
        # 1. Check Memory Session (Fastest)
        if st.session_state.get('connected'):
            return "AUTHENTICATED"

        # 2. Check Browser Cookies (Synchronous Fallback via st.context)
        try:
            # st.context.cookies is available in Streamlit 1.30+
            if hasattr(st, "context"):
                raw_cookies = getattr(st.context, "cookies", {})
                
                # CRITICAL DEBUG: Print to stdout so it shows in docker logs -f
                print(f"[AUTH_DEBUG] Cookies in st.context: {list(raw_cookies.keys())}")
                
                if self.cookie_name in raw_cookies:
                    import urllib.parse
                    import json
                    
                    raw_val = raw_cookies[self.cookie_name]
                    print(f"[AUTH_DEBUG] Found {self.cookie_name}, length: {len(raw_val)}")
                    
                    try:
                        # Try to decode URL-encoded JSON
                        decoded_val = urllib.parse.unquote(raw_val)
                        if decoded_val.startswith('{'):
                            user_info = json.loads(decoded_val)
                            
                            if user_info and 'email' in user_info:
                                print(f"[AUTH_DEBUG] Successfully authenticated {user_info['email']} via st.context")
                                st.session_state['connected'] = True
                                st.session_state['user_info'] = user_info
                                st.session_state['oauth_id'] = user_info.get('sub')
                                return "AUTHENTICATED"
                    except Exception as parse_e:
                        print(f"[AUTH_DEBUG] Cookie parse error: {parse_e}")
            else:
                print("[AUTH_DEBUG] st.context NOT available")
        except Exception as e:
            print(f"[AUTH_DEBUG] st.context search failed: {e}")
        
        # 3. Check CookieManager (Legacy/Compatibility Fallback)
        cookies = self.cookie_manager.get_all()
        
        cookie_retry_count = st.session_state.get('auth_cookie_retries', 0)
        
        # If we got here, st.context check failed. 
        # Log why if we have cookies from CookieManager
        if cookies and self.cookie_name in cookies:
            print(f"[AUTH_DEBUG] CookieManager found {self.cookie_name}, st.context missed it!")
            user_info = cookies[self.cookie_name]
            if user_info and 'email' in user_info:
                st.session_state['connected'] = True
                st.session_state['user_info'] = user_info
                st.session_state['oauth_id'] = user_info.get('sub')
                return "AUTHENTICATED"

        if cookies is None and cookie_retry_count < 2:
            st.session_state['auth_cookie_retries'] = cookie_retry_count + 1
            print(f"[AUTH_DEBUG] Returning LOADING (retry {cookie_retry_count+1})")
            return "LOADING"
        
        if cookies is not None:
             st.session_state['auth_cookie_retries'] = 0
             if self.cookie_name in cookies:
                try:
                    user_info = cookies[self.cookie_name]
                    if user_info and 'email' in user_info:
                        st.session_state['connected'] = True
                        st.session_state['user_info'] = user_info
                        st.session_state['oauth_id'] = user_info.get('sub')
                        return "AUTHENTICATED"
                except Exception:
                    pass

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
