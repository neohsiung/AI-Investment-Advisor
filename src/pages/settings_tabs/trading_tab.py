import streamlit as st
from src.repositories.settings_repository import SqliteSettingsRepository

def render_trading_tab(st, user_id: str):
    """
    Render Trading and Risk Management Settings.
    渲染交易與風控設定。
    """
    settings_repo = SqliteSettingsRepository()
    
    st.header("交易與風控設定 (Trading & Risk)")
    st.caption("設定主要券商與風險控制參數 (Configure Broker & Risk Limits)")
    
    # Fetch current settings
    current_broker = settings_repo.get(user_id, "preferred_broker") or "etoro"
    max_daily = settings_repo.get(user_id, "ai_max_daily_trades") or 10
    cb_loss = settings_repo.get(user_id, "cb_loss_streak") or 3
    sector_limit = settings_repo.get(user_id, "risk_max_sector_exposure") or 0.30
    trading_enabled = settings_repo.get(user_id, "ai_trading_enabled") or "true"
    
    # Kill Switch Status
    st.subheader("⚠️ 緊急開關 (Kill Switch)")
    if trading_enabled.lower() != "true":
        st.error("🔴 AI Trading is DISABLED (Kill Switch Active)")
        if st.button("🟢 Re-enable Trading"):
            settings_repo.set(user_id, "ai_trading_enabled", "true")
            st.rerun()
    else:
        st.success("🟢 AI Trading is ENABLED")
        if st.button("🔴 Emergency Stop (Kill Switch)"):
            settings_repo.set(user_id, "ai_trading_enabled", "false")
            st.rerun()

    st.divider()

    with st.form("trading_settings_form"):
        # Create Tabs for better organization
        tab_broker, tab_config, tab_risk = st.tabs(["🔌 券商連結 (Connections)", "⚙️ 交易參數 (Configuration)", "🛡️ 風控管理 (Risk)"])
        
        with tab_broker:
            st.subheader("券商連結設定 (Broker Connections)")
            st.caption("啟用並設定各券商的連線資訊 (Enable & Configure Brokers)")
            
            # Etoro Config
            with st.expander("eToro Settings", expanded=True):
                enable_etoro = st.checkbox("啟用 eToro (Enable eToro)", value=(settings_repo.get(user_id, "enable_etoro") == "true"))
                etoro_api_key = st.text_input("eToro API Key", value=settings_repo.get(user_id, "etoro_api_key") or "", type="password")
                etoro_user_key = st.text_input("eToro User Key", value=settings_repo.get(user_id, "etoro_user_key") or "", type="password")
                etoro_demo = st.checkbox("Demo Mode", value=(settings_repo.get(user_id, "etoro_mode") == "demo"))

            # Futu Config
            with st.expander("Futu OpenD Settings", expanded=False):
                enable_futu = st.checkbox("啟用 Futu (Enable Futu)", value=(settings_repo.get(user_id, "enable_futu") == "true"))
                futu_host = st.text_input("Futu Host", value=settings_repo.get(user_id, "futu_host") or "127.0.0.1")
                futu_port = st.number_input("Futu Port", value=int(settings_repo.get(user_id, "futu_port") or 11111))
                futu_pwd = st.text_input("Unlock Password (Optional)", value=settings_repo.get(user_id, "futu_pwd") or "", type="password")

            # IBKR Config
            with st.expander("Interactive Brokers Settings", expanded=False):
                enable_ibkr = st.checkbox("啟用 IBKR (Enable IBKR)", value=(settings_repo.get(user_id, "enable_ibkr") == "true"))
                ibkr_host = st.text_input("IBKR Host", value=settings_repo.get(user_id, "ibkr_host") or "127.0.0.1")
                ibkr_port = st.number_input("IBKR Port", value=int(settings_repo.get(user_id, "ibkr_port") or 7497))

        with tab_config:
            st.subheader("交易參數設定 (Trading Configuration)")
            col1, col2 = st.columns(2)
            with col1:
                new_broker = st.selectbox(
                    "選擇主要券商 (Preferred Broker)",
                    options=["etoro", "futu", "ibkr"],
                    index=["etoro", "futu", "ibkr"].index(current_broker) if current_broker in ["etoro", "futu", "ibkr"] else 0,
                    help="系統將使用此券商進行自動交易與資料同步。"
                )
            with col2:
                new_max_daily = st.number_input(
                    "每日最大交易次數 (Max Daily Trades)",
                    min_value=0, max_value=50, value=int(max_daily),
                    help="限制 Agent 每日可執行的最大交易筆數。"
                )
        
        with tab_risk:
            st.subheader("風控參數設定 (Risk Management)")
            col1, col2 = st.columns(2)
            with col1:
                new_sector_limit = st.slider(
                    "單一板塊曝險上限 (Max Sector Exposure)",
                    min_value=0.1, max_value=1.0, value=float(sector_limit), step=0.05,
                    format="%.0f%%"
                )
            with col2:
                new_cb_loss = st.number_input(
                    "連續虧損熔斷次數 (Circuit Breaker Loss Streak)",
                    min_value=1, max_value=10, value=int(cb_loss),
                    help="連續虧損達此次數後，自動停止交易。"
                )

        submitted = st.form_submit_button("儲存設定 (Save Settings)", use_container_width=True)
