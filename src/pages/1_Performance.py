import streamlit as st
import pandas as pd
import plotly.express as px
# from src.data.database import get_db_connection
# from src.analytics import update_daily_snapshot, PnLCalculator

def main():
    st.set_page_config(page_title="績效追蹤 | AI 投資顧問", layout="wide")

    st.title("績效追蹤 (Performance Tracking)")

    # --- Authentication Check ---
    from src.auth import auth_manager
    if not auth_manager.check_login():
        st.warning("請先登入 (Please login first)")
        st.stop()

    user = auth_manager.get_current_user()
    user_id = user['email']

    # Sidebar 設定
    st.sidebar.header("設定 (Settings)")
    db_path = st.sidebar.text_input("資料庫路徑 (Database Path)", "data/portfolio.db")

    # 初始化 Analytics Service
    from src.services.analytics_service import AnalyticsService
    analytics_service = AnalyticsService(db_path=db_path, user_id=user_id)

    # 自動更新今日績效快照
    try:
        analytics_service.trigger_snapshot_update()
    except Exception as e:
        st.warning(f"自動更新績效失敗 (Auto-update failed): {e}")

    # Mock Prices (應與 Dashboard 一致)
    current_prices = {
        "AAPL": 180.0, "NVDA": 450.0, "TSLA": 240.0, "GOOGL": 140.0, "MSFT": 370.0
    }

    try:
        pnl_data = analytics_service.get_pnl_breakdown(current_prices)
        st.subheader("損益分析 (PnL Analysis)")
        c1, c2, c3 = st.columns(3)
        c1.metric("已實現損益 (Realized P&L)", f"${pnl_data['realized']:,.2f}")
        c2.metric("未實現損益 (Unrealized P&L)", f"${pnl_data['unrealized']:,.2f}")
        c3.metric("總損益 (Total P&L)", f"${pnl_data['total']:,.2f}")
    except Exception as e:
        st.error(f"計算損益失敗: {e}")

    # 獲取歷史紀錄
    snapshots_df = analytics_service.get_performance_history()

    if snapshots_df is not None and not snapshots_df.empty:
        # A. 投入資本 vs 現值 (Bar Chart)
        latest = snapshots_df.iloc[-1]
        st.subheader("總投入資本 vs 當前價值 (Total Investment vs Current Value)")

        col1, col2 = st.columns(2)
        col1.metric("總投入資本 (Total Invested Capital)", f"${latest['invested_capital']:,.2f}")
        col2.metric("總損益 (Total PnL)", f"${latest['pnl']:,.2f}",
                    delta=f"{(latest['pnl']/latest['invested_capital']*100):.2f}%" if latest['invested_capital'] != 0 else "0%")

        # B. 權益曲線 (Line Chart)
        st.subheader("權益曲線 - 淨流動資產價值歷史 (Equity Curve - NLV History)")
        fig_equity = px.line(snapshots_df, x='date', y='total_nlv', title='淨流動資產價值 (Net Liquidation Value) 走勢', markers=True)
        st.plotly_chart(fig_equity, use_container_width=True)

        # C. 槓桿比率歷史 (Leverage History)
        if 'leverage_ratio' in snapshots_df.columns:
            st.subheader("槓桿比率歷史 (Leverage Ratio History)")
            fig_lev = px.line(snapshots_df, x='date', y='leverage_ratio', title='槓桿比率 (Leverage Ratio) 走勢', markers=True)
            # Add threshold lines
            fig_lev.add_hline(y=1.5, line_dash="dash", line_color="orange", annotation_text="Warning (1.5x)")
            fig_lev.add_hline(y=2.0, line_dash="dash", line_color="red", annotation_text="Critical (2.0x)")
            st.plotly_chart(fig_lev, use_container_width=True)

    else:
        st.info("尚無績效歷史紀錄。每日快照將由系統自動記錄。(No performance history yet.)")

if __name__ == "__main__":
    main()
