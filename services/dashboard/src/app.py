"""
Dashboard Page Module.
儀表板頁面模組。

Main entry point for the user dashboard, displaying real-time metrics,
positions, and asset allocation.
使用者儀表板的主要進入點，顯示即時指標、持倉及資產配置。
"""
import streamlit as st
import plotly.express as px
from src.data.database import init_db
from src.utils.ui import get_plotly_template
from src.utils.page_base import BasePage
from src.utils.components import saas_metric, saas_card_start, saas_card_end, saas_section_header, saas_alert
from src.services.dashboard_service import DashboardService
from src.utils.logger import setup_logger
from src.utils.tracing import init_tracing

# Initialize Tracing
init_tracing("dashboard")

logger = setup_logger("DashboardPage")

class DashboardPage(BasePage):
    """
    Main dashboard page.
    主要儀表板頁面。
    
    Displays:
    1. Key Metrics (NLV, Cash, Leverage, ROI)
    2. Real-time P&L (Realized/Unrealized)
    3. Current Holdings & Asset Allocation
    """
    
    def __init__(self):
        """Initialize Dashboard Page and Services."""
        super().__init__("總覽 (Overview)", "📊")
        self.dashboard_service = None  # Will be initialized in render()
    
    def render(self):
        """
        Render dashboard content.
        渲染儀表板內容。
        """
        user_id = self.user['id']
        
        # Initialize service on first render
        if self.dashboard_service is None:
            # Use db_path from BasePage (None will use environment DB_URL or DB_TYPE)
            db_path = getattr(self, 'db_path', None)
            self.dashboard_service = DashboardService(user_id=user_id, db_path=db_path)

        # High-level loading feedback for the entire Overview data preparation
        with st.spinner("總覽數據讀取中 (Overview Loading)..."):
            try:
                data = self.dashboard_service.prepare_dashboard_data(user_id)
                
                metrics = data['metrics']
                pnl_data = data['pnl_data']
                roi = data['roi']
                transactions_df = data['transactions_df']
                current_prices = data['current_prices']
                positions_df = data['positions_df']

                # --- Section 1: Metrics ---
                saas_section_header("系統概況與績效 (System Overview)", "即時資產概況與投報率指標")
                
                col1, col1b, col2, col3, col4, col5 = st.columns(6)
                with col1:
                    saas_metric("資產淨值 (NLV)", f"${metrics.get('nlv', 0):,.0f}", icon="💰",
                                help="您帳戶的總資產價值，包含「現金+持股市場價值+浮動盈虧」。")
                with col1b:
                    saas_metric("總曝險 (Gross)", f"${metrics.get('gross_nlv', 0):,.0f}", icon="📈",
                                help="系統控制的名義資產總額。包含槓桿後的部位總價值與現金，反映真實風險敞口。")
                with col2:
                    saas_metric("可用現金 (Cash)", f"${metrics.get('cash_balance', 0):,.0f}", icon="💵",
                                help="您帳戶中尚未用於購買資產的美元資金。用於支付保證金、隔夜費或做為建立新部位的資金。")
                with col3:
                    lev_ratio = metrics.get('leverage_ratio', 0)
                    lev_color = "normal" if lev_ratio < 2.0 else "inverse"
                    saas_metric("槓桿比率 (Lev)", f"{lev_ratio:.2f}x", delta_color=lev_color, icon="⚖️",
                                help="總曝險與資產淨值的比率。反映資金放大程度與風險密集度。")
                with col4:
                    saas_metric("總投報率 (ROI)", f"{roi:.2f}%", icon="📈",
                                help="累積盈虧相對於淨投入本金的百分比回報率。")
                with col5:
                    total_pnl = pnl_data.get('total', 0)
                    unrealized_pnl = pnl_data.get('unrealized', 0)
                    saas_metric("獲利/虧損 (P/L)", f"${total_pnl:,.0f}", 
                                delta=f"浮動: ${unrealized_pnl:,.0f}", icon="📊",
                                help="所有未平倉部位的即時價值與開倉時的價值差異。包含已實現利息、紅利和未實現漲跌。")

                if metrics.get('leverage_ratio', 0) >= 2.0:
                    saas_alert("危險警告: 槓桿比率過高！有追繳保證金風險 (Margin Call Risk)。", style="danger", title="槓桿風險警告")
                elif metrics.get('leverage_ratio', 0) >= 1.5:
                    saas_alert("警告: 槓桿比率偏高 (Leverage Ratio is high)。", style="warning")

                # --- Section 2: Positions ---
                saas_section_header("資產配置與清單 (Positions)", "即時資產持倉與槓桿明細")

                if not positions_df.empty:
                    cola, colb = st.columns([2.5, 1])
                    with cola:
                        saas_card_start(title="持倉明細 (Holdings)", icon="📋")
                        # Detailed Columns for Leverage Transparency
                        display_df = positions_df.rename(columns={
                            'ticker': '代號',
                            'quantity': '數量',
                            'current_price': '市價',
                            'leverage': '槓桿',
                            'gross_mv': '總價值',
                            'loan': '貸款',
                            'net_equity': '淨權益'
                        })
                        # Specify column order explicitly
                        cols_order = ['代號', '數量', '市價', '槓桿', '總價值', '貸款', '淨權益']
                        st.dataframe(display_df[cols_order].style.format({
                            "數量": "{:.2f}", 
                            "市價": "{:.2f}", 
                            "槓桿": "{:.1f}x",
                            "總價值": "{:.0f}",
                            "貸款": "{:.0f}",
                            "淨權益": "{:.0f}"
                        }), use_container_width=True)
                        saas_card_end()
                    
                    with colb:
                        valid_pie_data = positions_df[positions_df['gross_mv'] > 0]
                        if not valid_pie_data.empty:
                            saas_card_start(title="分佈 (Allocation)", icon="🥧")
                            template, layout_overrides = get_plotly_template()
                            fig = px.pie(valid_pie_data, values='gross_mv', names='ticker', template=template)
                            fig.update_layout(**layout_overrides)
                            fig.update_layout(margin=dict(t=10, b=10, l=10, r=10), showlegend=False)
                            st.plotly_chart(fig, use_container_width=True)
                            saas_card_end()
                        else:
                            st.info("無法顯示分佈圖")
                            zero_mv = positions_df[positions_df['gross_mv'] <= 0]
                            if not zero_mv.empty:
                                st.warning(f"目前無法取得以下資產價格: {zero_mv['ticker'].tolist()} (Prices not found)")
                else:
                    st.info("尚無持倉紀錄 (No active positions found)。")

                # --- Section 3: Broker Breakdown (Unified View) ---
                broker_breakdown = data.get('broker_breakdown', {})
                if broker_breakdown:
                    saas_section_header("券商資產分佈 (Broker Breakdown)", "各券商帳戶概況")
                    
                    b_cols = st.columns(len(broker_breakdown))
                    for idx, (b_name, account) in enumerate(broker_breakdown.items()):
                        with b_cols[idx]:
                            saas_card_start(title=f"{b_name.upper()}", icon="🏦")
                            st.metric("總權益 (Equity)", f"${account.total_equity:,.0f}")
                            st.metric("現金 (Cash)", f"${account.available_cash:,.0f}")
                            saas_card_end()

            except Exception as e:
                st.error(f"儀表板畫面渲染錯誤: {e}")
                
        # Debug / Maintenance Section
        with st.expander("🔧 除錯與維護 (Debug & Maintenance)"):
             st.write("Current User:", user_id)
             if st.button("清除快取 (Clear Cache)"):
                 st.cache_data.clear()
                 st.success("快取已清除，請重新整理頁面。")
             
             if 'active_tickers' in locals() and active_tickers:
                 st.write("Active Tickers:", active_tickers)
                 st.write("Current Prices:", self.dashboard_service._fetch_market_prices(active_tickers))
                 
             st.write("### API Key Status")
             import os
             keys = ["POLYGON_API_KEY", "FMP_API_KEY", "TAVILY_API_KEY", "FRED_API_KEY"]
             status = {k: "✅ Loaded" if os.getenv(k) else "❌ Missing" for k in keys}
             st.write(status)
             st.info("若無法取得價格，可能是 API 額度用盡或數據異常 (例如回傳 0)。請檢查 API Key 或稍後再試。")


if __name__ == "__main__":
    DashboardPage().run()
