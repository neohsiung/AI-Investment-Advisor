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
        st.subheader("參數配置 (Configuration)")
        col1, col2 = st.columns(2)
        
        with col1:
            new_broker = st.selectbox(
                "選擇主要券商 (Preferred Broker)",
                options=["etoro", "futu", "ibkr"],
                index=["etoro", "futu", "ibkr"].index(current_broker) if current_broker in ["etoro", "futu", "ibkr"] else 0,
                help="系統將使用此券商進行自動交易與資料同步。"
            )
            new_sector_limit = st.number_input(
                "單一板塊曝險上限 (Max Sector Exposure %)",
                min_value=0.1, max_value=1.0, value=float(sector_limit), step=0.05,
                help="單一板塊持倉佔總資產的最大比例 (0.1 ~ 1.0)。"
            )
        
        with col2:
            new_max_daily = st.number_input(
                "每日最大交易次數 (Max Daily Trades)",
                min_value=1, max_value=100, value=int(max_daily),
                help="超過此限制後，Risk Manager 將暫停當日交易。"
            )
            new_cb_loss = st.number_input(
                "連續虧損熔斷 (Loss Streak Limit)",
                min_value=1, max_value=20, value=int(cb_loss),
                help="連續虧損達此次數後，自動停止交易。"
            )

        submitted = st.form_submit_button("儲存設定 (Save Settings)")
        if submitted:
            settings_repo.set(user_id, "preferred_broker", new_broker)
            settings_repo.set(user_id, "ai_max_daily_trades", str(new_max_daily))
            settings_repo.set(user_id, "cb_loss_streak", str(new_cb_loss))
            settings_repo.set(user_id, "risk_max_sector_exposure", str(new_sector_limit))
            st.success(f"設定已儲存! 券商: {new_broker}, Sector Limit: {new_sector_limit:.0%}")
            st.rerun()
