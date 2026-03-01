"""
Base Page Template for the application.
應用程式的基礎頁面樣板。

Implements the Template Method Pattern to ensure consistent structure,
styles, and authentication across all pages.
實作樣板方法模式 (Template Method Pattern)，確保所有頁面擁有一致的結構、樣式與驗證機制。
"""
import streamlit as st
from abc import ABC, abstractmethod
from dotenv import load_dotenv

# Load environment variables (Robustness for local run)
load_dotenv()

class BasePage(ABC):
    """
    Abstract base class for all application pages.
    所有應用程式頁面的抽象基底類別。
    
    Enforces a standard lifecycle:
    強制執行標準生命週期：
    1. setup_page() - Page config & styles (頁面設定與樣式)
    2. handle_auth() - Authentication check (身分驗證檢查)
    3. render_sidebar() - Navigation & Sidebar (導覽列與側邊欄)
    4. render() - Main template method (主要樣板方法)
    """
    
    def __init__(self, title, icon, layout="wide"):
        """
        Initialize the page configuration.
        初始化頁面設定。
        
        Args:
            title (str): Page browser tab title. (瀏覽器頁籤標題)
            icon (str): Page favicon. (頁面圖示)
            layout (str): Streamlit layout mode ('centered' or 'wide'). (Streamlit 版面模式)
        """
        self.title = title
        self.icon = icon
        self.layout = layout
    
    def _cleanup_session_state(self):
        """
        Debug session state to identify persistent widgets.
        Currently disabled active cleanup to prevent blank pages.
        
        除錯 Session State 以識別殘留的元件狀態。
        目前已停用主動清除功能，以防止發生白畫面問題。
        """
        # Log session keys for debugging (Session keys 除錯紀錄)
        # print(f"DEBUG: Session keys on {self.title}: {list(st.session_state.keys())}")
        pass
    
    def setup_page(self):
        """
        Configure Streamlit page settings and load custom CSS.
        設定 Streamlit 頁面組態並載入自訂 CSS。
        """
        from src.data.database import init_db
        from src.utils.ui import load_design_system_css

        # Ensure Database Schema is up to date (Migration/Patching)
        init_db()
        
        st.set_page_config(
            page_title=self.title,
            page_icon=self.icon,
            layout=self.layout
        )
        
        # Load Design System CSS with Theme Support
        load_design_system_css()
        
        # Cleanup session state from other pages (optional/careful)
        # 清除來自其他頁面的 Session State (選用/需謹慎)
        self._cleanup_session_state()

    def handle_auth(self):
        """
        Check authentication logic. Stop execution if not authorized.
        檢查身分驗證邏輯。若未驗證通過則停止執行。
        """
        from src.utils.auth_guard import require_authentication
        self.user = require_authentication()

    def render_sidebar(self):
        """
        Render the common sidebar.
        渲染共用的側邊欄。
        """
        from src.utils.ui import render_sidebar
        self.db_path = render_sidebar(self.user)

    def render_header(self):
        """
        Render the page header using SaaS style.
        """
        from src.utils.ui import render_top_profile
        from src.utils.components import saas_section_header
        
        render_top_profile(self.user)
        saas_section_header(self.title, icon=self.icon)

    @abstractmethod
    def render(self):
        """
        Main logic for the specific page. Must be implemented by subclasses.
        特定頁面的主要邏輯。必須由子類別實作。
        """
        pass

    def run(self):
        """
        Main execution method (Template Method).
        主要執行方法 (樣板方法)。
        
        Orchestrates the page lifecycle.
        協調頁面生命週期。
        """
        self.setup_page()
        self.handle_auth()
        self.render_sidebar()
        
        # Main content container (Isolated Context)
        # 主要內容容器 (獨立隔離環境)
        with st.container():
            self.render_header()
            self.render()

