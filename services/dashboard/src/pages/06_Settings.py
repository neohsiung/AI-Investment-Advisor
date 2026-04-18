import streamlit as st
import time
from src.data.database import get_db_connection
from src.services.settings_service import SettingsService
from src.auth import auth_manager
from src.utils.page_base import BasePage

# Import modularized tab components
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
        super().__init__("系統設定 (System Settings)", ":material/tune:")
    
    def render(self):
        """
        Render settings content with robust navigation routing.
        """
        # 🚨 DIAGNOSTIC LOG
        print(f"DEBUG [SettingsPage]: render called at {time.strftime('%H:%M:%S')}")
        
        user_id = self.user['id']
        db_path = self.db_path

        # 1. Define Navigation Labels
        nav_options = [
            ":material/forum: 互動通知",
            ":material/candlestick_chart: 交易風控",
            ":material/api: 數據源",
            ":material/model_training: AI 模型",
            ":material/schedule: 排程",
            ":material/emergency: 風險詞",
            ":material/science: 實驗室",
            ":material/settings: 系統",
        ]
        
        # 2. Persist Navigation State
        if 'settings_nav' not in st.session_state:
            st.session_state['settings_nav'] = nav_options[0]

        # 3. Horizontal navigation bar
        selected_nav = st.radio(
            "設定導覽", 
            options=nav_options, 
            horizontal=True, 
            label_visibility="collapsed",
            key="settings_nav"
        )
        
        st.markdown("---")
        
        # 🚨 DIAGNOSTIC LOG - Core User Tracking
        print(f"DEBUG [SettingsPage]: Navigated to '{selected_nav}' for user_id='{user_id}'")
        
        settings_service = SettingsService(db_path, user_id=user_id)

        # 4. Content Content Routing (Explicit Isolation)
        if selected_nav == nav_options[0]: # Interaction
            render_channel_tab(st, settings_service, user_id)
        
        elif selected_nav == nav_options[1]: # Trading
            render_trading_tab(st, user_id)
            
        elif selected_nav == nav_options[2]: # Data Sources
            render_data_sources_tab(st, settings_service, user_id)
            
        elif selected_nav == nav_options[3]: # AI Model
            st.info(
                "🔧 **AI 模型設定已移至全新的 Next.js 介面。**\n\n"
                "請前往 Next.js 前端 `/settings` 頁面的「AI 引擎」Tab 管理：\n"
                "- **Providers**：新增/編輯 LLM 供應商（OpenRouter / OpenAI / Gemini / Ollama / Anthropic / Groq）\n"
                "- **Models**：管理各 Provider 底下的模型（手動新增或 Discover from Provider）\n"
                "- **Tier Bindings**：綁定 4 個 Tier（nano / fast / smart / advanced）的主模型與 fallback 鏈\n"
                "- **Agent Overrides**：為特定 Agent（CIO、SkillRouter 等）覆寫 Tier 綁定\n\n"
                "📄 操作手冊：`docs/runbook/llm_settings_user_guide.md`"
            )
            st.caption("若您無法存取 Next.js 前端，請聯絡管理員。")
            
        elif selected_nav == nav_options[4]: # Scheduler
            render_scheduler_tab(st, db_path, user_id=user_id)
            
        elif selected_nav == nav_options[5]: # Risk Keywords
            render_risk_keywords_tab(st, db_path)
            
        elif selected_nav == nav_options[6]: # Science (Agent Playground)
            st.info("此區域包含開發與測試工具。")
            sub_tabs = st.tabs([":material/smart_toy: Agent", ":material/draft: 試跑", ":material/auto_fix_high: Prompt"])
            with sub_tabs[0]: render_agent_playground_tab(st)
            with sub_tabs[1]: render_report_dry_run_tab(st, user_id)
            with sub_tabs[2]: render_optimization_history_tab(st, db_path, user_id)
            
        elif selected_nav == nav_options[7]: # System Core
            sub_tabs = st.tabs([":material/palette: 外觀", ":material/monitor_heart: HR", ":material/storage: 存儲"])
            with sub_tabs[0]: render_appearance_tab(st)
            with sub_tabs[1]: render_hr_protocol_tab(st)
            with sub_tabs[2]: render_storage_tab(st, db_path)

        # 🚨 DIAGNOSTIC LOG
        print(f"DEBUG [SettingsPage]: render completed for {selected_nav}")

if __name__ == "__main__":
    SettingsPage().run()
