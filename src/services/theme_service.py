import streamlit as st
import os
import json
from typing import Optional, Dict, Any, Tuple

class ThemeService:
    """
    Service for managing theme colors, CSS, and Plotly templates for the Streamlit dashboard.
    為 Streamlit 儀表板管理主題顏色、CSS 與 Plotly 模板的服務。
    """
    
    @staticmethod
    def get_current_theme() -> str:
        """
        Get the current theme from session state, defaulting to 'light'.
        從會話狀態獲取目前主題，預設為 'light'。
        """
        return st.session_state.get('theme', 'light')

    @staticmethod
    def load_theme_data(theme_name: str) -> Optional[Dict[str, Any]]:
        """
        Load theme color mappings from a local JSON configuration file.
        從本機 JSON 設定檔載入主題顏色映射。
        """
        try:
            current_file = os.path.abspath(__file__)
            # Adjust path to find src/styles/themes/
            theme_path = os.path.join(os.path.dirname(os.path.dirname(current_file)), 'styles', 'themes', f'{theme_name}.json')
            if os.path.exists(theme_path):
                with open(theme_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
        except Exception:
            pass
        return None

    @staticmethod
    def get_fallback_theme_data(theme_name: str) -> Dict[str, Any]:
        """
        Provide standard fallback theme data if the JSON configuration is missing.
        如果 JSON 設定缺失，則提供標準的備援主題數據。
        """
        return {
             "colors": {
                 "primary": "#0D9488" if theme_name == 'light' else "#14B8A6",
                 "bg": "#F8FAFC" if theme_name == 'light' else "#0B1120",
                 "card_bg": "#FFFFFF" if theme_name == 'light' else "#1E293B",
                 "sidebar_bg": "#F1F5F9" if theme_name == 'light' else "#0F172A",
                 "border": "#E2E8F0" if theme_name == 'light' else "#334155",
                 "text_main": "#1E293B" if theme_name == 'light' else "#F8FAFC",
                 "text_muted": "#64748B" if theme_name == 'light' else "#94A3B8"
             }
         }

    def get_plotly_template(self) -> Tuple[str, Dict[str, Any]]:
        """
        Return the Plotly template name and layout overrides based on the current theme.
        根據目前主題返回 Plotly 模板名稱與佈局覆蓋設定。
        """
        theme = self.get_current_theme()
        is_dark = (theme == 'dark')
        template = "plotly_dark" if is_dark else "plotly_white"
        
        c = self.load_theme_data(theme) or self.get_fallback_theme_data(theme)
        colors = c["colors"]
        
        layout_overrides = dict(
            paper_bgcolor='rgba(0,0,0,0)',
            plot_bgcolor='rgba(0,0,0,0)',
            font=dict(color=colors['text_main'], family='Inter, sans-serif'),
            xaxis=dict(gridcolor=colors['border'], zerolinecolor=colors['border']),
            yaxis=dict(gridcolor=colors['border'], zerolinecolor=colors['border']),
            margin=dict(t=30, b=30, l=30, r=30)
        )
        return template, layout_overrides

    def generate_theme_css(self) -> Tuple[str, str, Dict[str, Any]]:
        """
        Generate the unified CSS variable block and return theme details.
        產生統一的 CSS 變數區塊並返回主題詳情。
        """
        theme_name = self.get_current_theme()
        theme_data = self.load_theme_data(theme_name) or self.get_fallback_theme_data(theme_name)
        c = theme_data["colors"]
        
        return f"""
        :root {{
            --saas-primary: {c['primary']} !important;
            --saas-bg: {c['bg']} !important;
            --saas-card-bg: {c['card_bg']} !important;
            --saas-sidebar-bg: {c['sidebar_bg']} !important;
            --saas-border: {c['border']} !important;
            --saas-text-main: {c['text_main']} !important;
            --saas-text-muted: {c['text_muted']} !important;

            --primary-color: {c['primary']} !important;
            --background-color: {c['bg']} !important;
            --secondary-background-color: {c['sidebar_bg']} !important;
            --text-color: {c['text_main']} !important;
            --font: 'Inter', sans-serif !important;
        }}
        
        html, body, [data-testid="stHeader"], .stApp {{
            background-color: var(--saas-bg) !important;
            color: var(--saas-text-main) !important;
        }}
        [data-testid="stSidebar"] {{
            background-color: var(--saas-sidebar-bg) !important;
        }}
        [data-testid="stMarkdownContainer"] p, 
        [data-testid="stMarkdownContainer"] li,
        [data-testid="stMarkdownContainer"] span,
        [data-testid="stSidebarNav"] span {{
            color: var(--saas-text-main) !important;
        }}
        .stTextInput input, .stSelectbox [data-baseweb="select"], .stTextArea textarea, .stNumberInput input {{
            background-color: {c['card_bg']} !important;
            color: {c['text_main']} !important;
            border: 1px solid {c['border']} !important;
            border-radius: 8px !important;
        }}
        .stButton button, .stPageLink {{
            background-color: {c['card_bg']} !important;
            border: 1px solid {c['border']} !important;
            color: {c['text_main']} !important;
            border-radius: 8px !important;
            font-weight: 500 !important;
        }}
        .stButton button:hover, .stPageLink:hover {{
            background-color: {c['primary']}1A !important;
            border-color: var(--saas-primary) !important;
            color: var(--saas-primary) !important;
        }}
        .stButton button[kind="primary"], 
        .stButton button[kind="primaryFormSubmit"],
        .stButton button[data-testid="baseButton-primary"] {{
            background: {c['primary']} !important;
            color: white !important;
            border: none !important;
            font-weight: 600 !important;
        }}
        .stButton button[kind="primary"]:hover,
        .stButton button[kind="primaryFormSubmit"]:hover {{
            opacity: 0.9 !important;
            box-shadow: 0 4px 12px {c['primary']}33 !important;
        }}
        button[data-testid="stFormSubmitButton"], .stFormSubmitButton button {{
            background-color: {c['primary']} !important;
            color: white !important;
            border: none !important;
        }}
        header[data-testid="stHeader"] {{
            background-color: transparent !important;
        }}
        header[data-testid="stHeader"] button {{
            color: var(--saas-text-muted) !important;
        }}
        header[data-testid="stHeader"] button:hover {{
            color: var(--saas-primary) !important;
        }}
        """, theme_name, c
