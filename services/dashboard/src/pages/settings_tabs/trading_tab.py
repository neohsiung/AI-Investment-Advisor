from src.utils.components import saas_card_start, saas_card_end
from src.repositories.settings_repository import AlchemySettingsRepository
import time

def render_trading_tab(st, user_id: str):
    """
    Render Trading and Risk Management Settings.
    渲染交易與風控設定。
    """
    settings_repo = AlchemySettingsRepository()
    
    saas_card_start(title="Trading & Risk Hub", subtitle="配置主要券商與風險控制參數 (Configure Broker & Risk Limits)", icon="📊")
    
    # Fetch current settings
    current_broker = settings_repo.get(user_id, "preferred_broker") or "etoro"
    max_daily = settings_repo.get(user_id, "ai_max_daily_trades") or 10
    cb_loss = settings_repo.get(user_id, "cb_loss_streak") or 3
    sector_limit = settings_repo.get(user_id, "risk_max_sector_exposure") or 0.30
    trading_enabled = settings_repo.get(user_id, "ai_trading_enabled") or "true"
    risk_profile = settings_repo.get(user_id, "risk_profile") or "Balanced"
    target_cash = settings_repo.get(user_id, "target_cash_ratio") or 0.1
    
    # [NEW] Confidence Thresholds (Milestone 13.2)
    auto_threshold = settings_repo.get(user_id, "auto_trade_threshold") or 9
    auto_min_threshold = settings_repo.get(user_id, "auto_trade_min_threshold") or 3
    emer_score = settings_repo.get(user_id, "emergency_liquidation_score") or 9
    hedge_score = settings_repo.get(user_id, "auto_hedge_score") or 8
    
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

    with st.form("trading_form"):
        # Create Tabs for better organization
        tab_broker, tab_config, tab_risk = st.tabs([":material/link: 券商連結", ":material/tune: 交易參數", ":material/shield: 風控管理"])
        
        with tab_broker:
            st.write("##### 券商帳號設定")
            # Etoro Config
            with st.expander("🔹 eToro Settings", expanded=True):
                enable_etoro = st.checkbox("啟用 eToro (Enable eToro)", value=(settings_repo.get(user_id, "enable_etoro") == "true"))
                etoro_api_key = st.text_input("eToro API Key", value=settings_repo.get(user_id, "etoro_api_key") or "", type="password")
                etoro_user_key = st.text_input("eToro User Key", value=settings_repo.get(user_id, "etoro_user_key") or "", type="password")
                etoro_demo = st.checkbox("Demo Mode", value=(settings_repo.get(user_id, "etoro_mode") == "demo"))


            # IBKR Config
            with st.expander("🔹 Interactive Brokers Settings", expanded=False):
                enable_ibkr = st.checkbox("啟用 IBKR (Enable IBKR)", value=(settings_repo.get(user_id, "enable_ibkr") == "true"))
                ibkr_host = st.text_input("IBKR Host", value=settings_repo.get(user_id, "ibkr_host") or "127.0.0.1")
                ibkr_port = st.number_input("IBKR Port", value=int(settings_repo.get(user_id, "ibkr_port") or 7497))

            # FinancialData.Net Config
            with st.expander("🌐 FinancialData.Net (Backup Source)", expanded=False):
                financialdata_api_key = st.text_input(
                    "FinancialData.Net API Key", 
                    value=settings_repo.get(user_id, "financialdata_api_key") or "", 
                    type="password",
                    help="Free plan: 300 requests/day. Used for Insider Trading & Fallback quotes."
                )

        with tab_config:
            st.write("##### 自動交易設定")
            col1, col2 = st.columns(2)
            with col1:
                new_broker = st.selectbox(
                    "主要交易券商",
                    options=["etoro", "ibkr"],
                    index=["etoro", "ibkr"].index(current_broker) if current_broker in ["etoro", "ibkr"] else 0,
                    help="系統將優先使用此券商執行指令"
                )
            with col1:
                new_max_daily = st.number_input(
                    "每日最大筆數",
                    min_value=0, max_value=50, value=int(max_daily),
                    help="AI 每日允許執行的最大交易筆數，防止過度交易。"
                )
            
            st.write("---")
            st.write("##### 信心評分與自動執行 (Confidence Scoring)")
            st.info(
                "💡 **三段式閥值邏輯**：\n"
                "- 低於『最低通報閾值』→ 靜默跳過，不發送任何通知\n"
                "- 介於兩閾值之間 → 通知所有啟用管道，等待使用者核准\n"
                "- 高於『自動執行閾值』→ 直接自動執行買賣操作"
            )
            col_min, col_max = st.columns(2)
            with col_min:
                new_auto_min_threshold = st.slider(
                    "最低通報閾值 (Min)",
                    min_value=1, max_value=10, value=int(auto_min_threshold),
                    help="低於此值的評估結果將不會產生任何通知，靜默跳過。"
                )
            with col_max:
                new_auto_threshold = st.slider(
                    "自動執行信心閥值 (1-10)",
                    min_value=1, max_value=10, value=int(auto_threshold),
                    help="代理授權門檻。若 AI 信心評分低於此值但高於最低通報閾值，交易將進入『人工審核』流程。"
                )
            
            # Validation: min <= max
            if new_auto_min_threshold > new_auto_threshold:
                st.warning("⚠️ 最低通報閾值不得大於自動執行閾值，將自動修正。")
                new_auto_min_threshold = new_auto_threshold
        
        with tab_risk:
            st.write("##### 權益防護設定")
            col1, col2 = st.columns(2)
            with col1:
                # v5.1: Convert decimal to percentage for display (0.3 -> 30)
                # v5.1: 將小數轉換為整數百分比顯示 (0.3 -> 30)
                display_sector = int(float(sector_limit) * 100)
                new_sector_pct = st.slider(
                    "單一板塊曝險上限",
                    min_value=10, max_value=100, value=display_sector, step=5,
                    format="%d%%",
                    help="限制單一產業佔總資產的最高比例。例如 30% 代表科技股合共不得超過淨值的三成。"
                )
                new_sector_limit = new_sector_pct / 100.0
            with col2:
                new_cb_loss = st.number_input(
                    "連續虧損熔斷 (次)",
                    min_value=1, max_value=10, value=int(cb_loss),
                    help="當帳戶發生連續 N 次虧損交易時，將自動關閉 AI 交易開關以暫停策略執行。"
                )

            st.write("---")
            st.write("##### 🛡️ 進階風險屬性 (Risk Profile)")
            col_rp1, col_rp2 = st.columns(2)
            with col_rp1:
                new_risk_profile = st.selectbox(
                    "投資風險屬性",
                    options=["Balanced", "Aggressive"],
                    index=0 if risk_profile == "Balanced" else 1,
                    help="Balanced: 槓桿上限 1.70x。Aggressive: 槓桿上限 2.5x。"
                )
            with col_rp2:
                # Dynamic indicator from FRED if available
                from src.services.fred_service import FredService
                fred = FredService()
                macro = fred.get_macro_indicators()
                cpi = macro.get("CPI", {}).get("value", "N/A")
                st.metric("當前通膨引導 (CPI)", f"{cpi}", delta="FRED Data", delta_color="off")

            st.write("---")
            st.write("##### 💵 現金比例管理 (Cash Management)")
            st.info("💡 系統將根據『通膨率』與『市場波動』動態調整實際現金門檻。")
            new_target_cash_pct = st.slider(
                "目標基本現金比例 (%)",
                min_value=0, max_value=50, value=int(float(target_cash) * 100),
                format="%d%%",
                help="手動設定的基本現金水位。哨兵將基於此數值進行動態校準。"
            )
            new_target_cash = new_target_cash_pct / 100.0
            
            st.write("---")
            st.write("##### 🚨 Sentinel 緊急事件評分")
            st.caption("當系統偵測到行情異常時，預設帶入的虛擬評分。")
            col_e, col_h = st.columns(2)
            with col_e:
                 new_emer_score = st.number_input(
                     "緊急清倉信心分數", 
                     min_value=1, max_value=10, value=int(emer_score),
                     help="當偵測到極度風險 (如 VIX 飆升) 時，哨兵提議『出清持倉』所使用的評分。若大於自動執行閥值，則會主動清倉。"
                )
            with col_h:
                 new_hedge_score = st.number_input(
                     "自動避險信心分數", 
                     min_value=1, max_value=10, value=int(hedge_score),
                     help="當偵測到市場恐慌時，哨兵提議『買入 SQQQ 避險』所使用的評分。"
                )

        if st.form_submit_button("💾 儲存交易設定", use_container_width=True):
            try:
                def to_bool(v):
                    if isinstance(v, bool): return v
                    return str(v).lower() == "true"

                updates = {
                    "preferred_broker": new_broker,
                    "ai_max_daily_trades": new_max_daily,
                    "cb_loss_streak": new_cb_loss,
                    "risk_max_sector_exposure": new_sector_limit,
                    "auto_trade_threshold": new_auto_threshold,
                    "auto_trade_min_threshold": new_auto_min_threshold,
                    "emergency_liquidation_score": new_emer_score,
                    "auto_hedge_score": new_hedge_score,
                    "enable_etoro": enable_etoro,
                    "etoro_api_key": etoro_api_key,
                    "etoro_user_key": etoro_user_key,
                    "etoro_mode": "demo" if etoro_demo else "real",
                    "enable_ibkr": enable_ibkr,
                    "ibkr_host": ibkr_host,
                    "ibkr_port": ibkr_port,
                    "financialdata_api_key": financialdata_api_key,
                    "risk_profile": new_risk_profile,
                    "target_cash_ratio": new_target_cash
                }
                # v4.1.1: Don't use str(v) for all values - it double-encodes strings
                # v4.1.1: 不要對所有值使用 str(v) - 這會導致字串被雙重編碼
                for k, v in updates.items():
                    settings_repo.set(user_id, k, v)
                st.success("✅ 交易設定已更新")
                time.sleep(2)  # 延長顯示時間讓使用者看到成功訊息
                st.rerun()
            except Exception as e:
                st.error(f"❌ 儲存設定時發生錯誤: {str(e)}")
                st.exception(e)  # 顯示完整錯誤堆疊
                # 不執行 rerun，讓錯誤訊息保留在頁面上

    saas_card_end()
