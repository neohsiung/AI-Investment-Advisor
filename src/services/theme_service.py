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
        is_light = (theme_name == 'light')
        return {
             "colors": {
                 "primary": "#0D9488" if is_light else "#14B8A6",
                 "primary_light": "#CCFBF1" if is_light else "#134E4A",
                 "primary_gradient": "linear-gradient(135deg, #0D9488, #14B8A6)" if is_light else "linear-gradient(135deg, #14B8A6, #2DD4BF)",
                 "bg": "#F8FAFC" if is_light else "#0B1120",
                 "card_bg": "#FFFFFF" if is_light else "#1E293B",
                 "sidebar_bg": "#F1F5F9" if is_light else "#0F172A",
                 "border": "#E2E8F0" if is_light else "#334155",
                 "text_main": "#1E293B" if is_light else "#F1F5F9",
                 "text_muted": "#64748B" if is_light else "#94A3B8",
                 "success": "#10B981" if is_light else "#34D399",
                 "success_bg": "rgba(16, 185, 129, 0.08)" if is_light else "rgba(52, 211, 153, 0.12)",
                 "warning": "#D97706" if is_light else "#FBBF24",
                 "warning_bg": "rgba(217, 119, 6, 0.08)" if is_light else "rgba(251, 191, 36, 0.12)",
                 "danger": "#DC2626" if is_light else "#F87171",
                 "danger_bg": "rgba(220, 38, 38, 0.08)" if is_light else "rgba(248, 113, 113, 0.12)",
                 "info": "#2563EB" if is_light else "#60A5FA",
                 "info_bg": "rgba(37, 99, 235, 0.08)" if is_light else "rgba(96, 165, 250, 0.12)",
                 "input_bg": "#FFFFFF" if is_light else "#1E293B",
                 "hover_bg": "#F1F5F9" if is_light else "#334155",
                 "shadow": "0 1px 3px rgba(0,0,0,0.08)" if is_light else "0 1px 3px rgba(0,0,0,0.3)",
                 "shadow_hover": "0 10px 15px -3px rgba(0,0,0,0.08)" if is_light else "0 10px 15px -3px rgba(0,0,0,0.3)",
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

            /* Semantic Colors (Theme-Aware) */
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
            background-color: var(--saas-input-bg) !important;
            color: var(--saas-text-main) !important;
            border: 1px solid var(--saas-border) !important;
            border-radius: 8px !important;
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
            box-shadow: 0 4px 12px {c['primary']}33 !important;
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
        """, theme_name, c
