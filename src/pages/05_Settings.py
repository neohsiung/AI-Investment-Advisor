import streamlit as st
import pandas as pd
import requests
import sys
import subprocess # nosec B404
import os
import time
import json
from sqlalchemy import text
from src.data.database import get_db_connection
from src.services.settings_service import SettingsService
from src.agents.engineer import SystemEngineerAgent
from src.auth import auth_manager
from src.utils.page_base import BasePage


def render_api_settings(st, service: SettingsService, settings: dict):
    st.subheader("AI 模型參數 (AI Model Parameters)")

    with st.form("ai_settings_form"):
        provider_options = {
            "Google Gemini": "Google Gemini (Google AI)",
            "OpenRouter": "OpenRouter (Router)",
            "OpenAI": "OpenAI (OpenAI)"
        }
        current_provider = settings.get("AI_PROVIDER", "Google Gemini")
        # Ensure current provider is in options, mostly it is
        if current_provider not in provider_options:
            provider_index = 0
        else:
            provider_index = list(provider_options.keys()).index(current_provider)

        provider_key = st.selectbox(
            "AI 提供者 (Provider)",
            options=list(provider_options.keys()),
            format_func=lambda x: provider_options[x],
            index=provider_index
        )
        provider = provider_key

        st.markdown("### 模型分級設定 (Model Tiering)")
        st.info("請為不同任務需求設定合適的模型。Smart Tier 用於深度分析，Fast Tier 用於快速篩選。")

        # Smart Model
        smart_default = settings.get("AI_MODEL_SMART", settings.get("AI_MODEL", "gemini-1.5-pro"))
        st.markdown("#### 🧠 Smart Tier (智囊團)")
        st.caption("適用角色: CIO, Macro, Fundamental, Engineer")
        
        if provider == "OpenRouter":
             if 'openrouter_models' not in st.session_state:
                st.session_state['openrouter_models'] = []
             
             col_model, col_btn = st.columns([3, 1])
             with col_btn:
                if st.form_submit_button("更新模型列表 (Fetch Models)"):
                    st.session_state['openrouter_models'] = service.fetch_openrouter_models()
                    st.rerun()

             with col_model:
                if st.session_state['openrouter_models']:
                    if smart_default not in st.session_state['openrouter_models']:
                        st.session_state['openrouter_models'].insert(0, smart_default)
                    model_smart = st.selectbox("Smart Model", st.session_state['openrouter_models'], index=st.session_state['openrouter_models'].index(smart_default))
                else:
                    model_smart = st.text_input("Smart Model", value=smart_default)
        else:
            model_smart = st.text_input("Smart Model", value=smart_default, help="e.g., gemini-1.5-pro, gpt-4o")

        # Fast Model
        fast_default = settings.get("AI_MODEL_FAST", "gemini-1.5-flash")
        st.markdown("#### ⚡ Fast Tier (前鋒部隊)")
        st.caption("適用角色: Momentum, Dispatcher, Daily Check")
        
        if provider == "OpenRouter" and st.session_state.get('openrouter_models'):
             if fast_default not in st.session_state['openrouter_models']:
                st.session_state['openrouter_models'].insert(0, fast_default)
             model_fast = st.selectbox("Fast Model", st.session_state['openrouter_models'], index=st.session_state['openrouter_models'].index(fast_default))
        else:
            model_fast = st.text_input("Fast Model", value=fast_default, help="e.g., gemini-1.5-flash, gpt-4o-mini")

        api_key = st.text_input(
            "API Key",
            value=settings.get("API_KEY", ""),
            type="password",
            help="請輸入對應 Provider 的 API Key"
        )

        base_url = st.text_input(
            "Base URL (Optional)",
            value=settings.get("BASE_URL", ""),
            help="若使用 OpenRouter 或自定義端點請填寫，否則留空"
        )

        submitted = st.form_submit_button("儲存設定 (Save Settings)")

        if submitted:
            updates = {
                "AI_PROVIDER": provider,
                "AI_MODEL": model_smart, # Write to legacy/default as Smart
                "AI_MODEL_SMART": model_smart,
                "AI_MODEL_FAST": model_fast,
                "API_KEY": api_key,
                "BASE_URL": base_url
            }
            success, msg = service.save_settings_bulk(updates)
            if success:
                st.success(msg)
            else:
                st.error(msg)

def render_scheduler_tab(st, db_path):
    st.subheader("一般設定 (General Settings)")
    
    # Timezone Setting
    from src.services.settings_service import SettingsService
    import pytz
    import datetime
    
    sys_settings_service = SettingsService(db_path, user_id='SYSTEM')
    current_settings = sys_settings_service.get_all_settings()
    current_tz = current_settings.get("DISPLAY_TIMEZONE", "Asia/Taipei")
    
    common_timezones = ['Asia/Taipei', 'UTC', 'US/Eastern', 'US/Pacific', 'Europe/London', 'Asia/Tokyo']
    if current_tz not in common_timezones:
        common_timezones.append(current_tz)
        
    with st.expander("時區設定 (Timezone)", expanded=False):
        new_tz = st.selectbox("顯示時區 (Display Timezone)", 
                             options=common_timezones + [tz for tz in pytz.common_timezones if tz not in common_timezones],
                             index=0 if current_tz not in common_timezones and current_tz not in pytz.common_timezones else \
                                   (common_timezones + [tz for tz in pytz.common_timezones if tz not in common_timezones]).index(current_tz))
        
        if st.button("更新時區 (Update Timezone)"):
            success, msg = sys_settings_service.save_setting('DISPLAY_TIMEZONE', new_tz)
            if success:
                st.success(f"已更新時區為: {new_tz}")
                time.sleep(1)
                st.rerun()
            else:
                st.error(f"更新失敗: {msg}")

    st.markdown("---")
    st.subheader("排程設定 (Schedule Configuration)")

    # 讀取目前排程設定
    from src.agents.engineer import SystemEngineerAgent
    engineer = SystemEngineerAgent()
    config = engineer.get_schedule_config()
    
    # Days Mapping
    days_map = {
        "monday": "週一 (Mon)", "tuesday": "週二 (Tue)", "wednesday": "週三 (Wed)",
        "thursday": "週四 (Thu)", "friday": "週五 (Fri)", "saturday": "週六 (Sat)", "sunday": "週日 (Sun)"
    }
    reverse_days_map = {v: k for k, v in days_map.items()}

    with st.form("schedule_config_form"):
        st.info(f"排程時間基準為: **{sys_settings_service.get_setting('DISPLAY_TIMEZONE', 'Asia/Taipei')}**")

        # Start Daily Section
        st.markdown("#### 📅 每日檢查排程 (Daily Check)")
        col_d1, col_d2 = st.columns([1, 2])
        
        with col_d1:
            daily_time_val = pd.to_datetime(config.get("schedule_daily", "09:00"), format="%H:%M").time()
            daily_time = st.time_input("檢查時間 (Time)", value=daily_time_val)
            
            # Smart Default Logic
            is_early_morning = daily_time.hour < 12
            if is_early_morning:
                default_days_logic = ["tuesday", "wednesday", "thursday", "friday", "saturday"]
                smart_hint = "建議: 凌晨執行適合選週二至週六 (對應美股收盤)"
            else:
                default_days_logic = ["monday", "tuesday", "wednesday", "thursday", "friday"]
                smart_hint = "建議: 晚間執行適合選週一至週五 (當日數據)"
                
        with col_d2:
            current_daily_days_str = config.get("schedule_daily_days", "monday,tuesday,wednesday,thursday,friday")
            current_daily_days = [d.strip() for d in current_daily_days_str.split(",") if d.strip()]
            
            # Map to display names
            default_options = [days_map.get(d, d) for d in current_daily_days if d in days_map]
            all_options = list(days_map.values())
            
            daily_days_selected = st.multiselect(
                "執行日 (Select Days)",
                options=all_options,
                default=default_options,
                help=f"{smart_hint} (Smart Suggestion Active)"
            )
            st.caption(f"💡 {smart_hint}")

        st.markdown("---")
        
        # Start Weekly Section
        st.markdown("#### 📊 每週報告排程 (Weekly Report)")
        col_w1, col_w2 = st.columns(2)
        
        with col_w1:
            res_day = config.get("schedule_weekly_day", "saturday")
            weekly_day = st.selectbox("每週報告日 (Day)",
                                     options=list(days_map.keys()),
                                     format_func=lambda x: days_map[x],
                                     index=list(days_map.keys()).index(res_day) if res_day in days_map else 5)
        
        with col_w2:
             weekly_time = st.time_input("生成時間 (Time)",
                                        value=pd.to_datetime(config.get("schedule_weekly", "09:00"), format="%H:%M").time())

        st.markdown("")
        
        if st.form_submit_button("更新設定 (Update Schedule)"):
            try:
                # Convert Display Names back to keys
                selected_keys = [reverse_days_map[d] for d in daily_days_selected]
                # Sort them roughly by week order using keys list
                order_lookup = list(days_map.keys())
                selected_keys.sort(key=lambda x: order_lookup.index(x) if x in order_lookup else 99)
                
                engineer.set_schedule_config(
                    daily_time=daily_time.strftime("%H:%M"), 
                    weekly_time=weekly_time.strftime("%H:%M"), 
                    weekly_day=weekly_day,
                    daily_days=selected_keys
                )
                
                # Trigger Scheduler Reload via DB Signal
                sys_settings = SettingsService(db_path, user_id='SYSTEM')
                sys_settings.save_setting('scheduler_reload_signal', 'true')
                
                st.success("排程設定已更新！已通知 Scheduler 重新載入。(Schedule updated! Reload signal sent.)")
                time.sleep(1)
                st.rerun() # Refresh to show saved state
            except Exception as e:
                st.error(f"更新失敗: {e}")

    st.markdown("---")
    st.subheader("排程執行紀錄 (Scheduler Execution Logs)")

    # Scheduler logs via Service
    from src.services.scheduler_service import SchedulerService
    scheduler_service = SchedulerService()
    try:
        logs_df = scheduler_service.get_execution_logs(limit=50)
        
        # Convert timestamp to user timezone
        from src.utils.time_utils import get_timezone
        user_tz = get_timezone()
        
        # Ensure timestamp is datetime
        logs_df['timestamp'] = pd.to_datetime(logs_df['timestamp'])
        
        # Determine if naive or aware. If naive, assume UTC then convert. If aware, convert direct.
        # DB usually stores naive ISO (UTC) or naive local.
        # Let's assume stored as UTC if naive.
        if logs_df['timestamp'].dt.tz is None:
             logs_df['timestamp'] = logs_df['timestamp'].dt.tz_localize('UTC')
        
        logs_df['timestamp'] = logs_df['timestamp'].dt.tz_convert(user_tz)
        
        st.dataframe(logs_df, use_container_width=True)
    except Exception as e:
        st.info("尚無排程紀錄 (No scheduler logs found).")

    if st.button("重新整理 (Refresh Logs)"):
        st.rerun()



def render_report_dry_run_tab(st, user_id):

    st.subheader("報告試跑 (Report Dry Run)")
    st.info("此功能將以 Dry Run 模式執行每週報告流程，不會發送 Email。")

    # 確保 logs 目錄存在
    log_dir = "logs"
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)

    log_file = os.path.join(log_dir, "dry_run.log")

    # 初始化 Session State
    if 'dry_run_pid' not in st.session_state:
        st.session_state['dry_run_pid'] = None

    # 檢查執行狀態
    is_running = False
    if st.session_state['dry_run_pid']:
        try:
            # 檢查 PID 是否存在 (僅適用於 Unix)
            os.kill(st.session_state['dry_run_pid'], 0)
            is_running = True
        except OSError:
            is_running = False
            st.session_state['dry_run_pid'] = None

    col_btn, col_status = st.columns([1, 3])

    with col_btn:
        if not is_running:
            if st.button("開始生成測試報告 (Start Dry Run)"):
                # 清空舊 Log
                with open(log_file, "w") as f:
                    f.write(f"Starting Dry Run for user: {user_id}...\n")

                # 非同步啟動, 傳入 user_id
                process = subprocess.Popen(
                    [sys.executable, "src/cli.py", "--mode", "weekly", "--dry-run", "--user_id", user_id],
                    stdout=open(log_file, "a"),
                    stderr=subprocess.STDOUT,
                    preexec_fn=os.setsid # 確保可以被追蹤
                ) # nosec B603
                st.session_state['dry_run_pid'] = process.pid
                st.rerun()
        else:
            st.button("執行中... (Running)", disabled=True)
            if st.button("強制停止 (Stop)"):
                try:
                    os.killpg(os.getpgid(st.session_state['dry_run_pid']), 15) # SIGTERM
                    st.session_state['dry_run_pid'] = None
                    with open(log_file, "a") as f:
                        f.write("\n[Process stopped by user]\n")
                    st.rerun()
                except Exception as e:
                    st.error(f"停止失敗: {e}")

    with col_status:
        if is_running:
            st.warning(f"正在執行中 (PID: {st.session_state['dry_run_pid']}) - 請點擊下方按鈕刷新日誌")
        else:
            st.success("目前無執行任務 (Idle)")

    st.markdown("---")
    st.subheader("執行日誌 (Execution Logs)")

    if st.button("刷新日誌 (Refresh Logs)"):
        pass # 僅觸發 Rerun

    # 讀取並顯示 Log
    if os.path.exists(log_file):
        with open(log_file, "r") as f:
            lines = f.readlines()
            # 顯示最後 50 行
            log_content = "".join(lines[-50:])
            st.code(log_content, language="plaintext")

            # 自動滾動到底部 (Streamlit 限制，只能盡量)
            if is_running:
                from src.utils.time_utils import get_current_time
                st.caption(f"Last updated: {get_current_time().strftime('%H:%M:%S')}")
    else:
        st.info("尚無日誌檔案。")

    # --- Email Settings & Test ---
    st.markdown("---")
    st.header("郵件設定與測試 (Email Settings & Test)")

    # import os is already at the top of tab3
    sender_email = os.getenv("SENDER_EMAIL", "Not Set")
    recipient_email = os.getenv("RECIPIENT_EMAIL", "Not Set")
    smtp_server = os.getenv("SMTP_SERVER", "smtp.gmail.com")

    col1, col2 = st.columns(2)
    with col1:
        st.info(f"**Sender:** {sender_email}")
        st.info(f"**Recipient:** {recipient_email}")
    with col2:
        st.info(f"**SMTP Server:** {smtp_server}")

    if st.button("發送測試郵件 (Send Test Email)"):
        from src.notifier import EmailNotifier
        import logging
        import io

        # Setup log capture
        log_capture_string = io.StringIO()
        ch = logging.StreamHandler(log_capture_string)
        ch.setLevel(logging.INFO)
        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
        ch.setFormatter(formatter)

        logger = logging.getLogger("EmailNotifier")
        logger.addHandler(ch)

        notifier = EmailNotifier()
        with st.spinner("Sending test email..."):
            success = notifier.send_report(
                "Test Email from AI Investment Advisor",
                "This is a test email to verify your SMTP settings.\n\nIf you received this, your email configuration is correct."
            )

        # Remove handler
        logger.removeHandler(ch)
        log_contents = log_capture_string.getvalue()

        if success:
            st.success("測試郵件發送成功！ (Test email sent successfully!)")
        else:
            st.error("測試郵件發送失敗 (Failed to send test email)")

        with st.expander("查看詳細日誌 (View Detailed Logs)", expanded=True):
            st.code(log_contents)

def render_agent_playground_tab(st):
    st.subheader("Agent 獨立測試 (Agent Playground)")
    st.info("在此測試個別 Agent 的反應與輸出。請確保已設定 API Key。")

    agent_options = {
        "Momentum": "Momentum (動能專家)",
        "Fundamental": "Fundamental (基本面專家)",
        "Macro": "Macro (總經專家)",
        "CIO": "CIO (投資長)",
        "Engineer": "Engineer (系統工程師)"
    }
    agent_key = st.selectbox("選擇 Agent (Select Agent)", options=list(agent_options.keys()), format_func=lambda x: agent_options[x])
    agent_type = agent_key

    default_context = ""
    if agent_type == "Momentum":
        default_context = """{
    "ticker": "AAPL",
    "price": 220.5,
    "indicators": {
        "rsi": 65.5,
        "macd": "bullish",
        "macd_val": 1.25
    }
}"""
    elif agent_type == "Fundamental":
        default_context = """{
    "ticker": "AAPL",
    "financials": {
        "market_cap": 3400000000000,
        "trailing_pe": 35.2,
        "forward_pe": 28.5,
        "revenue_growth": 0.05,
        "profit_margins": 0.26
    },
    "news": [
        "Apple Intelligence features rolling out in iOS 18.1 (https://...)",
        "Analyst raises price target on strong services growth (https://...)"
    ]
}"""
    elif agent_type == "Macro":
        default_context = """{
    "macro_data": {
        "^VIX": 15.2,
        "^TNX": 4.35,
        "SPY": 580.0
    }
}"""
    elif agent_type == "CIO":
        default_context = """{
    "macro_report": "## Macro Outlook\\nRisk-On environment supported by stable yields (4.35%) and low VIX (15.2).",
    "momentum_reports": [
        "AAPL: { 'signal': 'BUY', 'reasoning': 'RSI 65.5 indicates strong momentum but not overbought.' }",
        "NVDA: { 'signal': 'HOLD', 'reasoning': 'Consolidating after recent highs.' }"
    ],
    "fundamental_reports": [
        "AAPL: Strong services revenue growth (5%) supports premium valuation (PE 35.2).",
        "NVDA: AI demand remains robust, forward PE attractive."
    ],
    "leverage_ratio": 1.1
}"""
    elif agent_type == "Engineer":
        default_context = """{
    "cio_report": "## System Optimization Feedback\\nCIO suggests that Momentum Agent should include explicit Volume Analysis for better trend confirmation.",
    "target_agent_name": "Momentum"
}"""

    context_input = st.text_area("輸入測試 Context (JSON)", value=default_context, height=200)

    if st.button(f"執行 {agent_type} Agent"):
        import json
        try:
            context = json.loads(context_input)

            # 動態載入 Agent
            if agent_type == "Momentum":
                from src.agents.momentum import MomentumAgent
                agent = MomentumAgent()
            elif agent_type == "Fundamental":
                from src.agents.fundamental import FundamentalAgent
                agent = FundamentalAgent()
            elif agent_type == "Macro":
                from src.agents.macro import MacroAgent
                agent = MacroAgent()
            elif agent_type == "CIO":
                from src.agents.cio import CIOAgent
                agent = CIOAgent()
            elif agent_type == "Engineer":
                from src.agents.engineer import SystemEngineerAgent
                agent = SystemEngineerAgent()

            with st.spinner(f"Running {agent_type} Agent..."):
                response = agent.run(context)

            st.success("執行成功！")
            st.markdown("### Agent 輸出 (Output)")
            st.markdown(response)

            with st.expander("查看原始回應 (Raw Response)"):
                st.code(response)

        except json.JSONDecodeError:
            st.error("JSON 格式錯誤，請檢查 Context 輸入。")
        except Exception as e:
            st.error(f"執行失敗: {e}")

def render_optimization_history_tab(st, db_path, user_id):
    st.subheader("Prompt 優化紀錄 (Optimization History)")

    # Use SettingsService for data access
    from src.services.settings_service import SettingsService
    settings_service = SettingsService(db_path, user_id=user_id)
    
    try:
        history_df = settings_service.get_prompt_history(user_id)

        if history_df.empty:
            st.info("尚無優化紀錄。")
        else:
            for _, row in history_df.iterrows():
                # Convert History Timestamp
                ts_str = row['timestamp']
                try:
                    from src.utils.time_utils import get_timezone
                    user_tz = get_timezone()
                    dt = pd.to_datetime(ts_str)
                    if dt.tz is None:
                        dt = dt.tz_localize('UTC')
                    dt_display = dt.tz_convert(user_tz).strftime('%Y-%m-%d %H:%M:%S')
                except:
                    dt_display = ts_str

                with st.expander(f"{dt_display} - {row['target_agent']}"):
                    st.caption(f"**Reason:** {row['reason']}")
                    st.text("Prompt Diff:")
                    st.code(row['diff_content'], language="diff")
    except Exception as e:
        # If schema mismatch or first run
        st.warning(f"讀取紀錄失敗 (可能是新表結構尚未初始化): {e}")


class SettingsPage(BasePage):
    """System settings page"""
    
    def __init__(self):
        super().__init__("系統設定 (System Settings)", "⚙️")
    
    def render(self):
        """Render settings content"""
        user_id = self.user['email']
        user_name = self.user['name']
        db_path = self.db_path
        
        st.caption(f"User: {user_name}")
        
        tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs(["AI 模型設定 (AI Configuration)", "排程設定與紀錄 (Scheduler)", "報告試跑 (Report Dry Run)", "Agent 獨立測試 (Agent Playground)", "Prompt 優化 (Optimization)", "HR 協議 (System Health)"])

        from src.services.settings_service import SettingsService
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


def render_hr_protocol_tab(st):
    st.subheader("HR 協議 (HR Protocol) - Agent Health Monitor")
    st.info("監控 Agent 是否活躍。若 Agent 超過 7 天未進行任何回應 (Cache Update)，將被標記為 Zombie。")
    
    from src.services.hr_service import HRService
    hr_service = HRService()
    
    if st.button("刷新狀態 (Check Health)"):
        st.session_state['hr_check'] = True
        
    df = hr_service.check_agent_health()
    
    # Styling
    def highlight_status(val):
        color = ''
        if 'Zombie' in val:
            color = 'background-color: #ffcdd2' # Red
        elif 'Active' in val:
            color = 'background-color: #c8e6c9' # Green
        elif 'Missing' in val:
            color = 'background-color: #f5f5f5' # Grey
        elif 'Idle' in val:
            color = 'background-color: #fff9c4' # Yellow
        return color

    st.dataframe(df.style.applymap(highlight_status, subset=['Status']), use_container_width=True)
    
    st.markdown("### 處置建議")
    zombies = df[df['Status'].str.contains("Zombie")]
    if not zombies.empty:
        st.error(f"⚠️ 偵測到 {len(zombies)} 個 Zombie Agents! 建議檢查排程或手動觸發。")
        for _, z in zombies.iterrows():
            st.write(f"- **{z['Agent']}**: {z['Days Inactive']} 天無活動。")
    else:
        st.success("✅ 所有 Agent 運作正常 (All Systems Operational)")

if __name__ == "__main__":
    SettingsPage().run()
