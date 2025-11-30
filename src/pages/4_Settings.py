import streamlit as st
import pandas as pd
import requests
import subprocess
from src.database import get_db_connection

st.set_page_config(page_title="設定 | AI 投資顧問", layout="wide")

st.title("系統設定 (System Settings)")

# Sidebar 設定
st.sidebar.header("設定 (Settings)")
db_path = st.sidebar.text_input("資料庫路徑 (Database Path)", "data/portfolio.db")

def fetch_openrouter_models():
    """從 OpenRouter API 獲取模型列表"""
    try:
        response = requests.get("https://openrouter.ai/api/v1/models")
        if response.status_code == 200:
            data = response.json()
            # 提取模型 ID 並排序
            models = sorted([model["id"] for model in data["data"]])
            return models
        else:
            st.error(f"無法獲取模型列表 (Status: {response.status_code})")
            return []
    except Exception as e:
        st.error(f"連線 OpenRouter 失敗: {e}")
        return []

tab1, tab2, tab3, tab4 = st.tabs(["AI 模型設定 (AI Configuration)", "排程紀錄 (Scheduler Logs)", "報告試跑 (Report Dry Run)", "Agent 獨立測試 (Agent Playground)"])

with tab1:
    st.subheader("AI 模型參數 (AI Model Parameters)")
    
    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    
    # 讀取現有設定
    settings = {}
    try:
        rows = cursor.execute("SELECT key, value FROM settings").fetchall()
        for row in rows:
            settings[row[0]] = row[1]
    except Exception as e:
        st.error(f"讀取設定失敗: {e}")
    
    with st.form("ai_settings_form"):
        provider = st.selectbox(
            "AI 提供者 (Provider)", 
            ["Google Gemini", "OpenRouter", "OpenAI"],
            index=["Google Gemini", "OpenRouter", "OpenAI"].index(settings.get("AI_PROVIDER", "Google Gemini"))
        )
        
        # 動態模型選擇邏輯
        model_options = []
        if provider == "OpenRouter":
            # 如果 Session State 中已有列表則使用，否則提供按鈕獲取
            if 'openrouter_models' not in st.session_state:
                st.session_state['openrouter_models'] = []
            
            col_model, col_btn = st.columns([3, 1])
            with col_btn:
                if st.form_submit_button("更新模型列表 (Fetch Models)"):
                    st.session_state['openrouter_models'] = fetch_openrouter_models()
                    st.rerun() # 重新整理以更新下拉選單
            
            with col_model:
                if st.session_state['openrouter_models']:
                    current_model = settings.get("AI_MODEL", "google/gemini-pro-1.5")
                    # 確保當前模型在列表中，否則加入
                    if current_model not in st.session_state['openrouter_models']:
                        st.session_state['openrouter_models'].insert(0, current_model)
                    
                    model_name = st.selectbox(
                        "模型名稱 (Model Name)",
                        st.session_state['openrouter_models'],
                        index=st.session_state['openrouter_models'].index(current_model) if current_model in st.session_state['openrouter_models'] else 0
                    )
                else:
                    model_name = st.text_input(
                        "模型名稱 (Model Name)", 
                        value=settings.get("AI_MODEL", "google/gemini-pro-1.5"),
                        help="請點擊右側按鈕獲取列表，或手動輸入 (例如: google/gemini-pro-1.5)"
                    )
        else:
            # 其他 Provider 維持手動輸入
            model_name = st.text_input(
                "模型名稱 (Model Name)", 
                value=settings.get("AI_MODEL", "gemini-1.5-pro"),
                help="例如: gemini-1.5-pro, gpt-4o"
            )
        
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
            try:
                cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", ("AI_PROVIDER", provider))
                cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", ("AI_MODEL", model_name))
                cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", ("API_KEY", api_key))
                cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", ("BASE_URL", base_url))
                conn.commit()
                st.success("設定已儲存！(Settings saved successfully!)")
            except Exception as e:
                st.error(f"儲存失敗: {e}")
    
    conn.close()

with tab2:
    st.subheader("排程執行紀錄 (Scheduler Execution Logs)")
    
    conn = get_db_connection(db_path)
    try:
        logs_df = pd.read_sql("SELECT timestamp, job_name, status, message FROM scheduler_logs ORDER BY timestamp DESC LIMIT 50", conn)
        st.dataframe(logs_df, use_container_width=True)
    except Exception as e:
        st.info("尚無排程紀錄 (No scheduler logs found).")
    
    if st.button("重新整理 (Refresh Logs)"):
        st.rerun()
        
    conn.close()

import os
import time

with tab3:
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
                    f.write("Starting Dry Run...\n")
                
                # 非同步啟動
                process = subprocess.Popen(
                    ["python3", "src/workflow.py", "--mode", "weekly", "--dry-run"],
                    stdout=open(log_file, "a"),
                    stderr=subprocess.STDOUT,
                    preexec_fn=os.setsid # 確保可以被追蹤
                )
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
                st.caption(f"Last updated: {time.strftime('%H:%M:%S')}")
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

# --- Tab 4: Agent Playground ---

with tab4:
    st.subheader("Agent 獨立測試 (Agent Playground)")
    st.info("在此測試個別 Agent 的反應與輸出。請確保已設定 API Key。")
    
    agent_type = st.selectbox("選擇 Agent (Select Agent)", ["Momentum", "Fundamental", "Macro", "CIO"])
    
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
