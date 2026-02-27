"""
UI Helper Functions with Theme Support
"""
import streamlit as st
import os
from datetime import datetime
from src.services.theme_service import ThemeService

# Initialize Service
theme_service = ThemeService()

def safe_page_link(page: str, label: str, icon: str = None, help: str = None, use_container_width: bool = False):
    """
    Safely render a page link, falling back to a button + switch_page if st.page_link is unavailable (Streamlit < 1.31.0).
    """
    if hasattr(st, "page_link"):
        st.page_link(page, label=label, icon=icon, help=help, use_container_width=use_container_width)
    else:
        # Fallback for older Streamlit versions
        if st.button(f"{icon + ' ' if icon else ''}{label}", help=help, use_container_width=use_container_width):
            st.switch_page(page)

def safe_button(label: str, key: str = None, help: str = None, icon: str = None, use_container_width: bool = False, **kwargs):
    """
    Safely render a button, handling the 'icon' parameter which is only available in Streamlit >= 1.35.0.
    """
    from inspect import signature
    try:
        # Check if st.button accepts 'icon' argument
        sig = signature(st.button)
        if 'icon' in sig.parameters:
            return st.button(label, key=key, help=help, icon=icon, use_container_width=use_container_width, **kwargs)
        else:
            # Fallback for Streamlit < 1.35.0: Prepend icon to label
            display_label = f"{icon + ' ' if icon else ''}{label}"
            return st.button(display_label, key=key, help=help, use_container_width=use_container_width, **kwargs)
    except Exception:
        # Extreme fallback if signature check fails
        display_label = f"{icon + ' ' if icon else ''}{label}"
        return st.button(display_label, key=key, help=help, use_container_width=use_container_width, **kwargs)

def safe_html(body: str):
    """
    Safely render HTML, falling back to st.markdown with unsafe_allow_html=True if st.html is unavailable (Streamlit < 1.34.0).
    """
    if hasattr(st, "html"):
        st.html(body)
    else:
        st.markdown(body, unsafe_allow_html=True)

def get_plotly_template():
    """Return Plotly template and layout overrides based on current theme."""
    return theme_service.get_plotly_template()

def load_theme_from_json(theme_name):
    """Load theme color mapping from JSON file (Delegated to service)."""
    return theme_service.load_theme_data(theme_name)

def load_design_system_css():
    """Load theme-driven CSS deeply integrated via Streamlit and generic OS Media Queries."""
    # We no longer rely on python-side state for static theme application.
    # Theme Service now generates CSS vars for BOTH light and dark via media queries.
    theme_css, _, _ = theme_service.generate_theme_css()
    
    # Get absolute path to styles directory for base CSS
    current_file = os.path.abspath(__file__)
    styles_dir = os.path.join(os.path.dirname(os.path.dirname(current_file)), 'styles')
    ds_path = os.path.join(styles_dir, 'design_system.css')
    
    css_base = ""
    if os.path.exists(ds_path):
        with open(ds_path, 'r', encoding='utf-8') as f:
            css_base = f.read()

    # Inject static CSS using markdown
    st.markdown(f"<style>{css_base}\n{theme_css}</style>", unsafe_allow_html=True)

def render_theme_switcher(key_suffix="", icon_only=False):
    """Render a professional minimalist theme guideline."""
    if not icon_only:
        st.info("🌗 系統主題現已自動與您的作業系統 (OS) 同步。若需手動覆寫，請點擊螢幕右上角選單 (⋮) ➔ Settings ➔ Theme 進行切換。", icon="💡")

def load_theme_css(theme="light"):
    """Legacy fallback - delegated to main design system loader."""
    load_design_system_css()

def render_sidebar(user, default_db_path=None):
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
            
            # The Integrated Preference Row: [Profile/Settings | Logout]
            cols = st.columns([3.5, 1])
            
            with cols[0]:
                # Link to Settings page. Path is relative to dashboard.py/Main.py
                safe_page_link("pages/06_Settings.py", label=f"{short_name}. {display_name[:6]}...", icon="👤", help="User Settings")
            
            with cols[1]:
                if safe_button("", key="logout_v18", icon="🚪", help="Logout", use_container_width=True):
                    auth_manager.logout()
            
            st.divider()
            
    return None

def render_top_profile(user):
    """Deprecated - use render_sidebar instead."""
    pass
