from src.utils.components import saas_card_start, saas_card_end
from src.repositories.settings_repository import AlchemySettingsRepository
import time

def render_trading_tab(st, user_id: str):
    """
    Render Trading and Risk Management Settings.
    渲染交易與風控設定。
    """
    settings_repo = AlchemySettingsRepository()
    
    saas_card_start(title="Trading & Risk Hub", subtitle="配置主要券商與風險控制參數 (Configure Broker & Risk Limits)", icon="📈")
    
    # Fetch current settings
    current_broker = settings_repo.get(user_id, "preferred_broker") or "etoro"
    max_daily = settings_repo.get(user_id, "ai_max_daily_trades") or 10
    cb_loss = settings_repo.get(user_id, "cb_loss_streak") or 3
    sector_limit = settings_repo.get(user_id, "risk_max_sector_exposure") or 0.30
    trading_enabled = settings_repo.get(user_id, "ai_trading_enabled") or "true"
    
    # Kill Switch Status
    st.write("#### ⚠️ 緊急開關 (Kill Switch)")
    col_status, col_btn = st.columns([2, 1])
    with col_status:
        if trading_enabled.lower() != "true":
            st.error("🔴 AI Trading is DISABLED")
        else:
            st.success("🟢 AI Trading is ENABLED")
    
    with col_btn:
        if trading_enabled.lower() != "true":
            if st.button("🟢 Re-enable", use_container_width=True):
                settings_repo.set(user_id, "ai_trading_enabled", "true")
                st.rerun()
        else:
            if st.button("🔴 Emergency Stop", use_container_width=True):
                settings_repo.set(user_id, "ai_trading_enabled", "false")
                st.rerun()

    st.divider()

    with st.form("trading_settings_form"):
        # Create Tabs for better organization
        tab_broker, tab_config, tab_risk = st.tabs(["🔌 券商連結 (Connections)", "⚙️ 交易參數 (Configuration)", "🛡️ 風控管理 (Risk)"])
        
        with tab_broker:
            st.write("##### 券商帳號設定")
            # Etoro Config
            with st.expander("🔹 eToro Settings", expanded=True):
                enable_etoro = st.checkbox("啟用 eToro (Enable eToro)", value=(settings_repo.get(user_id, "enable_etoro") == "true"))
                etoro_api_key = st.text_input("eToro API Key", value=settings_repo.get(user_id, "etoro_api_key") or "", type="password")
                etoro_user_key = st.text_input("eToro User Key", value=settings_repo.get(user_id, "etoro_user_key") or "", type="password")
                etoro_demo = st.checkbox("Demo Mode", value=(settings_repo.get(user_id, "etoro_mode") == "demo"))

            # Futu Config
            with st.expander("🔹 Futu OpenD Settings", expanded=False):
                enable_futu = st.checkbox("啟用 Futu (Enable Futu)", value=(settings_repo.get(user_id, "enable_futu") == "true"))
                futu_host = st.text_input("Futu Host", value=settings_repo.get(user_id, "futu_host") or "127.0.0.1")
                futu_port = st.number_input("Futu Port", value=int(settings_repo.get(user_id, "futu_port") or 11111))
                futu_pwd = st.text_input("Unlock Password (Optional)", value=settings_repo.get(user_id, "futu_pwd") or "", type="password")

            # IBKR Config
            with st.expander("🔹 Interactive Brokers Settings", expanded=False):
                enable_ibkr = st.checkbox("啟用 IBKR (Enable IBKR)", value=(settings_repo.get(user_id, "enable_ibkr") == "true"))
                ibkr_host = st.text_input("IBKR Host", value=settings_repo.get(user_id, "ibkr_host") or "127.0.0.1")
                ibkr_port = st.number_input("IBKR Port", value=int(settings_repo.get(user_id, "ibkr_port") or 7497))

        with tab_config:
            st.write("##### 自動交易設定")
            col1, col2 = st.columns(2)
            with col1:
                new_broker = st.selectbox(
                    "主要交易券商",
                    options=["etoro", "futu", "ibkr"],
                    index=["etoro", "futu", "ibkr"].index(current_broker) if current_broker in ["etoro", "futu", "ibkr"] else 0,
                    help="系統將優先使用此券商執行指令"
                )
            with col2:
                new_max_daily = st.number_input(
                    "每日最大筆數",
                    min_value=0, max_value=50, value=int(max_daily)
                )
        
        with tab_risk:
            st.write("##### 權益防護設定")
            col1, col2 = st.columns(2)
            with col1:
                new_sector_limit = st.slider(
                    "單一板塊曝險上限",
                    min_value=0.1, max_value=1.0, value=float(sector_limit), step=0.05,
                    format="%.0f%%"
                )
            with col2:
                new_cb_loss = st.number_input(
                    "連續虧損熔斷 (次)",
                    min_value=1, max_value=10, value=int(cb_loss)
                )

        if st.form_submit_button("💾 儲存交易設定", use_container_width=True):
            updates = {
                "preferred_broker": new_broker,
                "ai_max_daily_trades": new_max_daily,
                "cb_loss_streak": new_cb_loss,
                "risk_max_sector_exposure": new_sector_limit,
                "enable_etoro": "true" if enable_etoro else "false",
                "etoro_api_key": etoro_api_key,
                "etoro_user_key": etoro_user_key,
                "etoro_mode": "demo" if etoro_demo else "live",
                "enable_futu": "true" if enable_futu else "false",
                "futu_host": futu_host,
                "futu_port": futu_port,
                "futu_pwd": futu_pwd,
                "enable_ibkr": "true" if enable_ibkr else "false",
                "ibkr_host": ibkr_host,
                "ibkr_port": ibkr_port
            }
            for k, v in updates.items():
                settings_repo.set(user_id, k, str(v))
            st.success("✅ 交易設定已更新")
            time.sleep(1)
            st.rerun()

    saas_card_end()
