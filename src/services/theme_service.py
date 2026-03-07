import streamlit as st
import os
import json
import typing
from typing import List, Dict, Tuple, Any, Optional, Callable, Dict, List, Tuple, Any, Optional, Callable

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
            theme_path = os.path.join(os.path.dirname(os.path.dirname(current_file)), 'styles', 'themes', f'{theme_name}.json')
            if os.path.exists(theme_path):
                with open(theme_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            pass
        return None

    @staticmethod
    def get_fallback_theme_data(theme_name: str) -> Dict[str, Any]:
        """
        Provide standard fallback theme data if the JSON configuration is missing.
        如果 JSON 設定缺失，則提供標準的備援主題數據。
        """
        is_light = (theme_name == 'light')
        return {
             "colors": {
                 "primary": "#6C5CE7" if is_light else "#A78BFA",
                 "primary_light": "#EDE9FE" if is_light else "#2E1065",
                 "primary_gradient": "linear-gradient(135deg, #6C5CE7, #A78BFA)" if is_light else "linear-gradient(135deg, #A78BFA, #7DD3FC)",
                 "bg": "#FAFBFC" if is_light else "#0A0E1A",
                 "card_bg": "#FFFFFF" if is_light else "#151929",
                 "sidebar_bg": "#F3F4F8" if is_light else "#0D1120",
                 "border": "#E5E7EB" if is_light else "#1E2640",
                 "text_main": "#1A1D2E" if is_light else "#E8ECF4",
                 "text_muted": "#6B7280" if is_light else "#8B95AD",
                 "success": "#059669" if is_light else "#34D399",
                 "success_bg": "rgba(5, 150, 105, 0.08)" if is_light else "rgba(52, 211, 153, 0.10)",
                 "warning": "#D97706" if is_light else "#FBBF24",
                 "warning_bg": "rgba(217, 119, 6, 0.08)" if is_light else "rgba(251, 191, 36, 0.10)",
                 "danger": "#E11D48" if is_light else "#FB7185",
                 "danger_bg": "rgba(225, 29, 72, 0.06)" if is_light else "rgba(251, 113, 133, 0.10)",
                 "info": "#2563EB" if is_light else "#60A5FA",
                 "info_bg": "rgba(37, 99, 235, 0.07)" if is_light else "rgba(96, 165, 250, 0.10)",
                 "input_bg": "#FFFFFF" if is_light else "#151929",
                 "hover_bg": "#F0F1F5" if is_light else "#1E2640",
                 "shadow": "0 1px 3px rgba(108, 92, 231, 0.06), 0 1px 2px rgba(0,0,0,0.04)" if is_light else "0 1px 3px rgba(0,0,0,0.4), 0 1px 2px rgba(0,0,0,0.3)",
                 "shadow_hover": "0 10px 25px -5px rgba(108, 92, 231, 0.12), 0 4px 6px -2px rgba(0,0,0,0.04)" if is_light else "0 10px 25px -5px rgba(167, 139, 250, 0.15), 0 4px 6px -2px rgba(0,0,0,0.3)",
             }
         }

    def get_plotly_template(self) -> Tuple[str, Dict[str, Any]]:
        """
        Return the Plotly template name and layout overrides based on CSS variables.
        根據 CSS 變數返回 Plotly 模板名稱與佈局覆蓋設定。
        """
        template = "plotly_white"
        
        layout_overrides = dict(
            paper_bgcolor='rgba(0,0,0,0)',
            plot_bgcolor='rgba(0,0,0,0)',
            font=dict(color='var(--saas-text-main)', family='Inter, sans-serif'),
            xaxis=dict(gridcolor='var(--saas-border)', zerolinecolor='var(--saas-border)'),
            yaxis=dict(gridcolor='var(--saas-border)', zerolinecolor='var(--saas-border)'),
            margin=dict(t=30, b=30, l=30, r=30)
        )
        return template, layout_overrides

    def generate_theme_css(self) -> Tuple[str, str, Dict[str, Any]]:
        """
        Generate the unified CSS variable block and return theme details.
        產生統一的 CSS 變數區塊並返回主題詳情。包含自動跟隨 OS 的 Media Queries。
        """
        light_data = self.load_theme_data("light") or self.get_fallback_theme_data("light")
        dark_data  = self.load_theme_data("dark")  or self.get_fallback_theme_data("dark")
        
        c_light = light_data["colors"]
        c_dark  = dark_data["colors"]
        
        def dict_to_css_vars(c):
            return f"""
            /* Core Palette */
            --saas-primary: {c['primary']} !important;
            --saas-primary-light: {c.get('primary_light', '#CCFBF1')};
            --saas-primary-gradient: {c.get('primary_gradient', c['primary'])};
            --saas-bg: {c['bg']} !important;
            --saas-card-bg: {c['card_bg']} !important;
            --saas-sidebar-bg: {c['sidebar_bg']} !important;
            --saas-border: {c['border']} !important;
            --saas-text-main: {c['text_main']} !important;
            --saas-text-muted: {c['text_muted']} !important;

            /* Semantic Colors */
            --saas-success: {c.get('success', '#10B981')} !important;
            --saas-success-bg: {c.get('success_bg', 'rgba(16,185,129,0.08)')};
            --saas-warning: {c.get('warning', '#F59E0B')} !important;
            --saas-warning-bg: {c.get('warning_bg', 'rgba(245,158,11,0.08)')};
            --saas-danger: {c.get('danger', '#EF4444')} !important;
            --saas-danger-bg: {c.get('danger_bg', 'rgba(239,68,68,0.08)')};
            --saas-info: {c.get('info', '#3B82F6')} !important;
            --saas-info-bg: {c.get('info_bg', 'rgba(59,130,246,0.08)')};

            /* Surfaces & Interaction */
            --saas-input-bg: {c.get('input_bg', c['card_bg'])};
            --saas-hover-bg: {c.get('hover_bg', c['sidebar_bg'])};
            --saas-shadow: {c.get('shadow', '0 1px 3px rgba(0,0,0,0.1)')};
            --saas-shadow-hover: {c.get('shadow_hover', '0 10px 15px -3px rgba(0,0,0,0.1)')};

            /* Streamlit Built-in Overrides */
            --primary-color: {c['primary']} !important;
            --background-color: {c['bg']} !important;
            --secondary-background-color: {c['sidebar_bg']} !important;
            --text-color: {c['text_main']} !important;
            --font: 'Inter', sans-serif !important;
            """
        
        css = f"""
        /* Light mode (default) */
        :root {{
            {dict_to_css_vars(c_light)}
        }}
        
        /* Dark mode */
        @media (prefers-color-scheme: dark) {{
            :root {{
                {dict_to_css_vars(c_dark)}
            }}
        }}
        
        /* Static CSS Overrides */
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
            background-color: var(--saas-input-bg) !important;
            color: var(--saas-text-main) !important;
            border: 1px solid var(--saas-border) !important;
            border-radius: 8px !important;
        }}
        /* Fix native streamlit metric styling for delta */
        [data-testid="stMetricDelta"] svg {{
            margin-right: 4px;
        }}
        .stButton button, .stPageLink {{
            background-color: var(--saas-card-bg) !important;
            border: 1px solid var(--saas-border) !important;
            color: var(--saas-text-main) !important;
            border-radius: 8px !important;
            font-weight: 500 !important;
        }}
        .stButton button:hover, .stPageLink:hover {{
            background-color: var(--saas-hover-bg) !important;
            border-color: var(--saas-primary) !important;
            color: var(--saas-primary) !important;
        }}
        .stButton button[kind="primary"], 
        .stButton button[kind="primaryFormSubmit"],
        .stButton button[data-testid="baseButton-primary"] {{
            background: var(--saas-primary) !important;
            color: white !important;
            border: none !important;
            font-weight: 600 !important;
        }}
        .stButton button[kind="primary"]:hover,
        .stButton button[kind="primaryFormSubmit"]:hover {{
            opacity: 0.9 !important;
            box-shadow: 0 4px 12px var(--saas-primary-light) !important;
        }}
        button[data-testid="stFormSubmitButton"], .stFormSubmitButton button {{
            background-color: var(--saas-primary) !important;
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
        /* Tabs */
        .stTabs [data-baseweb="tab-list"] {{
            background-color: transparent !important;
            gap: 2px;
        }}
        .stTabs [data-baseweb="tab"] {{
            color: var(--saas-text-muted) !important;
            background-color: transparent !important;
            border-radius: 8px 8px 0 0 !important;
        }}
        .stTabs [aria-selected="true"] {{
            color: var(--saas-primary) !important;
            border-bottom-color: var(--saas-primary) !important;
        }}
        /* Toggle / Checkbox */
        .stCheckbox label span {{
            color: var(--saas-text-main) !important;
        }}
        .stToggle label span {{
            color: var(--saas-text-main) !important;
        }}
        /* Expander */
        .streamlit-expanderHeader {{
            color: var(--saas-text-main) !important;
            background-color: var(--saas-card-bg) !important;
        }}
        [data-testid="stExpander"] {{
            border-color: var(--saas-border) !important;
        }}
        /* Multiselect */
        .stMultiSelect [data-baseweb="tag"] {{
            background-color: var(--saas-primary) !important;
            color: white !important;
        }}
        /* Dataframes base fix */
        [data-testid="stDataFrame"] {{
            background-color: var(--saas-card-bg) !important;
        }}
        """
        return css, "auto", c_light

