import streamlit as st
from src.data.database import get_db_connection
from src.services.settings_service import SettingsService
from src.auth import auth_manager
from src.utils.page_base import BasePage

# Import modularized tab components
from services.dashboard.src.pages.settings_tabs.ai_config_tab import render_api_settings
from services.dashboard.src.pages.settings_tabs.scheduler_tab import render_scheduler_tab
from services.dashboard.src.pages.settings_tabs.report_dry_run_tab import render_report_dry_run_tab
from services.dashboard.src.pages.settings_tabs.agent_playground_tab import render_agent_playground_tab
from services.dashboard.src.pages.settings_tabs.optimization_tab import render_optimization_history_tab
from services.dashboard.src.pages.settings_tabs.hr_protocol_tab import render_hr_protocol_tab
from services.dashboard.src.pages.settings_tabs.appearance_tab import render_appearance_tab
from services.dashboard.src.pages.settings_tabs.storage_tab import render_storage_tab
from services.dashboard.src.pages.settings_tabs.trading_tab import render_trading_tab
from services.dashboard.src.pages.settings_tabs.risk_keywords_tab import render_risk_keywords_tab
from services.dashboard.src.pages.settings_tabs.data_sources_tab import render_data_sources_tab

from services.dashboard.src.pages.settings_tabs.channel_tab import render_channel_tab

class SettingsPage(BasePage):
    """System settings page"""
    
    def __init__(self):
        super().__init__("系統設定 (System Settings)", "⚙️")
    
    def render(self):
        """
        Render settings content.
        渲染設定內容。
        """
        # v4.1: Use UUID instead of email for user_id
        # v4.1: 使用 UUID 而非 email 作為 user_id
        # auth_guard already resolves email to UUID and adds 'id' to user object
        user_id = self.user['id']
        db_path = self.db_path

        # 1. Define Tabs (Reordered by Usage Frequency)
        tab_names = [
            "互動與通知 (Interaction & Comms)", # P0: Channels & Alerts
            "交易與風控 (Trading & Risk)",      # P1: Broker & Risk
            "數據源矩陣 (Data Source Matrix)",  # P2: API Keys
            "AI 模型設定 (AI Models)",          # P3: LLM Config
            "排程與任務 (Scheduler)",           # P4: Automation
            "風險關鍵字 (Risk Keywords)",       # P5: Sentinel Config
            "開發者實驗室 (Dev Playground)",    # P6: Agent Test & Dry Run
            "系統核心 (System Core)"            # P7: HR, Storage, Appearance
        ]
        
        tabs = st.tabs(tab_names)
        
        # Unpack Tabs
        t_interaction = tabs[0]
        t_trading = tabs[1]
        t_data = tabs[2]
        t_ai = tabs[3]
        t_scheduler = tabs[4]
        t_risk_kw = tabs[5]
        t_playground = tabs[6]
        t_system = tabs[7]

        settings_service = SettingsService(db_path, user_id=user_id)

        # --- Tab 1: Interaction & Channels ---
        with t_interaction:
            render_channel_tab(st, settings_service, user_id)

        # --- Tab 2: Trading & Risk ---
        with t_trading:
            render_trading_tab(st, user_id)

        # --- Tab 3: Data Source Matrix ---
        with t_data:
            render_data_sources_tab(st, settings_service, user_id)

        # --- Tab 4: AI Configuration ---
        with t_ai:
            settings = settings_service.get_all_settings()
            render_api_settings(st, settings_service, settings)

        # --- Tab 5: Scheduler ---
        with t_scheduler:
            render_scheduler_tab(st, db_path)

        # --- Tab 6: Risk Keywords ---
        with t_risk_kw:
            render_risk_keywords_tab(st, db_path)

        # --- Tab 7: Developer Playground (Merged) ---
        with t_playground:
            st.info("此區域包含開發與測試工具。")
            sub_t1, sub_t2, sub_t3 = st.tabs(["Agent 測試 (Playground)", "報告試跑 (Dry Run)", "Prompt 優化"])
            
            with sub_t1:
                render_agent_playground_tab(st)
            with sub_t2:
                render_report_dry_run_tab(st, user_id)
            with sub_t3:
                render_optimization_history_tab(st, db_path, user_id)

        # --- Tab 8: System Core (Merged) ---
        with t_system:
            sub_t1, sub_t2, sub_t3 = st.tabs(["介面與主題 (Appearance)", "HR 協議 (Health)", "系統存儲 (Storage)"])
            
            with sub_t1:
                render_appearance_tab(st)
            with sub_t2:
                render_hr_protocol_tab(st)
            with sub_t3:
                render_storage_tab(st, db_path)

if __name__ == "__main__":
    SettingsPage().run()
