"""
UI Helper Functions with Theme Support
"""
import streamlit as st
import os
from datetime import datetime
from src.services.theme_service import ThemeService

# Initialize Service
theme_service = ThemeService()

def get_plotly_template():
    """Return Plotly template and layout overrides based on current theme."""
    return theme_service.get_plotly_template()

def load_theme_from_json(theme_name):
    """Load theme color mapping from JSON file (Delegated to service)."""
    return theme_service.load_theme_data(theme_name)

def load_design_system_css():
    """Load theme-driven CSS with deep Streamlit variable integration."""
    # Ensure theme is initialized
    if 'theme' not in st.session_state:
        st.session_state['theme'] = 'light'
    
    theme_css, theme_name, c = theme_service.generate_theme_css()
    
    # Get absolute path to styles directory for base CSS
    current_file = os.path.abspath(__file__)
    styles_dir = os.path.join(os.path.dirname(os.path.dirname(current_file)), 'styles')
    ds_path = os.path.join(styles_dir, 'design_system.css')
    
    css_base = ""
    if os.path.exists(ds_path):
        with open(ds_path, 'r', encoding='utf-8') as f:
            css_base = f.read()

    # Inject everything
    st.html(f"""
    <style>{css_base}\n{theme_css}</style>
    <script>
        (function() {{
            const theme = '{theme_name}';
            const apply = () => {{
                document.documentElement.setAttribute('data-theme', theme);
                localStorage.setItem('st-theme', theme);
                try {{
                    const root = window.parent.document.querySelector('.stApp');
                    if (root) {{
                        root.setAttribute('data-theme', theme);
                        root.style.backgroundColor = (theme === "dark") ? "{c['bg']}" : "{c['bg']}";
                    }}
                }} catch (e) {{}}
            }};
            apply();
            window.addEventListener('load', apply);
        }})();
    </script>
    """)

def render_theme_switcher(key_suffix="", icon_only=False):
    """Render a professional minimalist theme toggle."""
    theme = st.session_state.get('theme', 'light')
    new_theme = "dark" if theme == "light" else "light"
    label = "" if icon_only else ("Switch to Dark Mode" if theme == "light" else "Switch to Light Mode")
    icon = "🌙" if theme == "light" else "☀️"
    
    if st.button(label, use_container_width=True if not icon_only else False, key=f"toggle_{key_suffix}", icon=icon):
        st.session_state.theme = new_theme
        st.rerun()

def load_theme_css(theme="light"):
    """Legacy fallback - delegated to main design system loader."""
    load_design_system_css()

def render_sidebar(user, default_db_path="data/portfolio.db"):
    """Sleek minimalist sidebar with horizontal preference-centric navigation."""
    from src.auth import auth_manager
    
    with st.sidebar:
        if user:
            display_name = user.get('name', 'User')
            short_name = display_name[0].upper()
            
            # CSS for high-density preference row
            st.markdown("""
            <style>
                .saas-pref-row {
                    display: flex;
                    align-items: center;
                    gap: 0.5rem;
                    padding: 0.5rem 0;
                }
                [data-testid="column"] button, [data-testid="column"] a {
                    min-height: 32px !important;
                    height: 32px !important;
                    display: flex !important;
                    align-items: center !important;
                    justify-content: center !important;
                    padding: 0 8px !important;
                    border-radius: 8px !important;
                }
            </style>
            """, unsafe_allow_html=True)
            
            # The Integrated Preference Row: [Profile/Settings | Theme | Logout]
            cols = st.columns([2.5, 1, 1])
            
            with cols[0]:
                st.page_link("pages/Settings.py", label=f"{short_name}. {display_name[:6]}...", icon="👤", help="User Settings")
            
            with cols[1]:
                render_theme_switcher(key_suffix="sidebar_v15", icon_only=True)
                
            with cols[2]:
                if st.button("", key="logout_v15", icon="🚪", help="Logout", use_container_width=True):
                    auth_manager.logout()
            
            st.divider()
            
    return None

def render_top_profile(user):
    """Deprecated - use render_sidebar instead."""
    pass
