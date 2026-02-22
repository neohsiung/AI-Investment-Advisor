import streamlit as st
import plotly.express as px
from src.utils.page_base import BasePage
from src.utils.components import saas_metric, saas_card_start, saas_card_end, saas_section_header
from src.utils.ui import get_plotly_template
from src.services.performance_service import PerformanceService

class PortfolioPerformancePage(BasePage):
    """Portfolio performance tracking page"""
    
    def __init__(self):
        super().__init__("績效追蹤 (Performance Tracking)", "📈")
        self.perf_service = None # Init in render where user_id is available
    
    def render(self):
        """Render performance tracking content"""
        user_id = self.user['id']
        db_path = self.db_path
        
        self.perf_service = PerformanceService(db_path=db_path, user_id=user_id)

        with st.spinner("正在讀取市場數據 (Fetching performance data)..."):
            data = self.perf_service.prepare_performance_data()
            pnl_data = data.get('pnl_data', {'realized': 0, 'unrealized': 0, 'total': 0})
            snapshots_df = data.get('history_df')

        # --- Section 1: P&L ---
        saas_section_header("績效與損益分析 (Analysis)", "詳細損益明細與實現狀況")
        c1, c2, c3, c4 = st.columns(4)
        with c1:
            saas_metric("已實現損益 (Realized)", f"${pnl_data.get('realized', 0):,.0f}", icon="✅",
                        help="已平倉部位的獲利與收到的股息總和 (包含已實現利息、紅利與費用)。")
        with c2:
            saas_metric("獲利/虧損 (P/L)", f"${pnl_data.get('unrealized', 0):,.0f}", icon="⏳",
                        help="所有未平倉 (Open) 部位的目前即時價值與開倉時的價值差異。")
        with c3:
            saas_metric("累積淨損益 (Total)", f"${pnl_data.get('total', 0):,.0f}", delta_color="normal", icon="💰",
                        help="帳戶自成立以來的所有獲利總額。")
        
        # 顯示淨投入資本（從快照或計算）
        with c4:
            if snapshots_df is not None and not snapshots_df.empty:
                latest = snapshots_df.iloc[-1]
                invested_capital = latest.get('invested_capital', 0)
            else:
                # 如果沒有快照，嘗試從交易計算
                from src.repositories.transaction_repository import AlchemyTransactionRepository
                trans_repo = AlchemyTransactionRepository()
                invested_capital = trans_repo.calculate_net_invested_capital(user_id)
            saas_metric("持股現值 (Invested)", f"${invested_capital:,.0f}", icon="🏦",
                        help="所有交易、複製跟單及 Smart Portfolios 的當前投入資金淨額，不含未實現盈虧。")

        # --- Section 2: Trends & Charts ---
        if snapshots_df is not None and not snapshots_df.empty:

            saas_section_header("趨勢與風險 (Trends & Risk)", "長期資產增長與槓桿監控")
            
            # 檢查欄位名稱並標準化
            nlv_column = 'total_nlv' if 'total_nlv' in snapshots_df.columns else 'nlv'
            
            # NLV Chart
            saas_card_start(title="NLV 歷史增長 (Growth)")
            template, layout_overrides = get_plotly_template()
            fig_equity = px.area(snapshots_df, x='date', y=nlv_column, markers=False, color_discrete_sequence=['var(--saas-primary)'], template=template)
            fig_equity.update_layout(**layout_overrides)
            fig_equity.update_layout(
                height=180, 
                margin=dict(t=5, b=5, l=0, r=0),
                xaxis_title=None, yaxis_title=None,
                hovermode="x unified"
            )
            st.plotly_chart(fig_equity, use_container_width=True)
            saas_card_end()

            # Leverage Chart
            if 'leverage_ratio' in snapshots_df.columns:
                st.markdown('<div style="margin-top: 0.5rem;"></div>', unsafe_allow_html=True)
                saas_card_start(title="槓桿變動 (Leverage)")
                fig_lev = px.line(snapshots_df, x='date', y='leverage_ratio', markers=False, color_discrete_sequence=['var(--saas-text-muted)'], template=template)
                fig_lev.update_layout(**layout_overrides)
                fig_lev.update_layout(
                    height=180, 
                    margin=dict(t=5, b=5, l=0, r=0),
                    xaxis_title=None, yaxis_title=None,
                    hovermode="x unified"
                )
                fig_lev.add_hline(y=1.5, line_dash="dash", line_color="var(--saas-warning)")
                fig_lev.add_hline(y=2.0, line_dash="dash", line_color="var(--saas-danger)")
                st.plotly_chart(fig_lev, use_container_width=True)
                saas_card_end()
            else:
                st.info("快照資料中缺少槓桿比率欄位。")
        # --- Section 3: Tools ---
        st.markdown('<div style="margin-top: 2rem;"></div>', unsafe_allow_html=True)
        with st.expander("🛠️ 進階工具 (Advanced Tools)"):
            st.warning("修復快照功能將重新計算今日績效並更新數據。")
            if st.button("手動修復今日快照 (Repair Today's Snapshot)"):
                from src.services.analytics_service import AnalyticsService
                analytics = AnalyticsService(db_path=db_path, user_id=user_id)
                with st.spinner("正在修復中..."):
                    analytics.trigger_snapshot_update(force=True)
                st.success("今日快照已更新！請重新整理頁面。")
                st.rerun()

if __name__ == "__main__":
    PortfolioPerformancePage().run()
