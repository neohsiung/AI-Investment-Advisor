"""
UI Helper Functions with Theme Support
"""
import streamlit as st
import os
from src.auth import auth_manager

try:
    import darkdetect
    HAS_DARKDETECT = True
    # HAS_DARKDETECT = True # Commented out to ensure Time-based logic wins in Docker
except ImportError:
    pass # No need to set HAS_DARKDETECT = False here, as we'll set it below
HAS_DARKDETECT = False # Explicitly set to False to prioritize time-based logic


from datetime import datetime

def get_auto_theme():
    """Auto-detect theme - FORCED LIGHT per User Request"""
    return "light"

    # Legacy Logic Disabled:
    # if HAS_DARKDETECT:
    #     theme = darkdetect.theme()
    #     if theme: return theme.lower()
    # hour = datetime.now().hour
    # if 6 <= hour < 18: return "light"
    # return "dark"

    # return "dark"



def load_theme_css(theme="light"):
    """Load theme-specific CSS"""
    if theme == "auto":
        theme = "light" # Override auto to light
    
    # Get absolute path to styles directory
    current_file = os.path.abspath(__file__)
    utils_dir = os.path.dirname(current_file)
    src_dir = os.path.dirname(utils_dir)
    styles_dir = os.path.join(src_dir, 'styles')
    css_file = f'{theme}_theme.css'
    css_path = os.path.join(styles_dir, css_file)
    
    if os.path.isfile(css_path):
        with open(css_path, 'r', encoding='utf-8') as f:
            css_content = f.read()
            st.markdown(f'<style>{css_content}</style>', unsafe_allow_html=True)


def load_custom_css():
    """Load CSS based on user theme preference"""
    # Initialize theme in session state if not present
    if 'theme' not in st.session_state:
        st.session_state.theme = 'light' # Force Light
    
    # Override logic: Ensures it STAYS light regardless of previous auto/dark state
    if st.session_state.get('theme') != 'light':
        st.session_state.theme = 'light'

    theme = st.session_state.theme
    load_theme_css(theme)



def render_sidebar(user, default_db_path="data/portfolio.db"):
    """Professional sidebar with theme switcher"""
    with st.sidebar:
        # User info
        st.markdown(f"""
        <div style="padding: 1.25rem 0; border-bottom: 1px solid var(--border-primary); margin-bottom: 1rem;">
            <div style="font-size: 0.7rem; color: var(--text-muted); text-transform: uppercase; letter-spacing: 1px; margin-bottom: 0.5rem;">
                Portfolio Manager
            </div>
            <div style="font-size: 1rem; font-weight: 600; color: var(--text-primary); margin-bottom: 0.3rem;">
                {user['name']}
            </div>
            <div style="font-size: 0.8rem; color: var(--text-secondary);">
                {user['email']}
            </div>
        </div>
        """, unsafe_allow_html=True)
        
        # Theme switcher - DISABLED (Defaulting to Light for better UX)
        # theme_option = st.selectbox(
        #     "Theme",
        #     options=["auto", "light", "dark"],
        #     index=["auto", "light", "dark"].index(st.session_state.get('theme', 'auto')),
        #     help="Auto: Changes based on time of day",
        #     key="theme_selector"
        # )
        
        # if theme_option != st.session_state.get('theme', 'auto'):
        #     st.session_state.theme = theme_option
        #     st.rerun()

        # Force Light Theme (User Request: "All use light theme")
        if st.session_state.get('theme') != 'light':
             st.session_state.theme = 'light'
        
        # Logout
        if st.button("Logout", use_container_width=True, key="logout_btn"):
            auth_manager.logout()
        
        st.divider()
        
        # Settings
        st.markdown("""
        <div style="font-size: 0.75rem; font-weight: 600; color: var(--accent-primary); margin-bottom: 0.75rem; text-transform: uppercase; letter-spacing: 0.5px;">
            Settings
        </div>
        """, unsafe_allow_html=True)
        
        db_path = st.text_input(
            "Database Path",
            value=default_db_path,
            label_visibility="collapsed"
        )
        st.caption("📁 Database Path")
        
    return db_path
