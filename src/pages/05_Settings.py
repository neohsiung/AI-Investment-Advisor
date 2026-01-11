import streamlit as st
from src.data.database import get_db_connection
from src.services.settings_service import SettingsService
from src.auth import auth_manager
from src.utils.page_base import BasePage

# Import modularized tab components
from src.pages.settings_tabs.ai_config_tab import render_api_settings
from src.pages.settings_tabs.scheduler_tab import render_scheduler_tab
from src.pages.settings_tabs.report_dry_run_tab import render_report_dry_run_tab
from src.pages.settings_tabs.agent_playground_tab import render_agent_playground_tab
from src.pages.settings_tabs.optimization_tab import render_optimization_history_tab
from src.pages.settings_tabs.hr_protocol_tab import render_hr_protocol_tab
from src.pages.settings_tabs.appearance_tab import render_appearance_tab
from src.pages.settings_tabs.storage_tab import render_storage_tab

class SettingsPage(BasePage):
    """System settings page"""
    
    def __init__(self):
        super().__init__("系統設定 (System Settings)", "⚙️")
    
    def render(self):
        """Render settings content"""
        user_id = self.user['email']
        db_path = self.db_path

        tab1, tab2, tab3, tab4, tab5, tab6, tab7, tab8 = st.tabs([
            "AI 模型設定 (AI Configuration)", 
            "排程設定與紀錄 (Scheduler)", 
            "報告試跑 (Report Dry Run)", 
            "Agent 獨立測試 (Agent Playground)", 
            "Prompt 優化 (Optimization)", 
            "HR 協議 (System Health)",
            "介面與主題 (Appearance)",
            "系統存儲 (Storage)"
        ])

        settings_service = SettingsService(db_path, user_id=user_id)

        with tab1:
            settings = settings_service.get_all_settings()
            render_api_settings(st, settings_service, settings)
        
        with tab2:
            render_scheduler_tab(st, db_path)

        with tab3:
            render_report_dry_run_tab(st, user_id)

        with tab4:
            render_agent_playground_tab(st)

        with tab5:
            render_optimization_history_tab(st, db_path, user_id)

        with tab6:
            render_hr_protocol_tab(st)

        with tab7:
            render_appearance_tab(st)
            
        with tab8:
            render_storage_tab(st, db_path)

if __name__ == "__main__":
    SettingsPage().run()
