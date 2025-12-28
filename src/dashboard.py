"""
Dashboard Page Module.
儀表板頁面模組。

Main entry point for the user dashboard, displaying real-time metrics,
positions, and asset allocation.
使用者儀表板的主要進入點，顯示即時指標、持倉及資產配置。
"""
import streamlit as st
import pandas as pd
import plotly.express as px
from src.data.database import init_db
from src.services.analytics_service import LeverageCalculator, ROIEngine, update_daily_snapshot, PnLCalculator
from src.services.market_data_service import MarketDataService
from src.services.transaction_service import TransactionService
from src.repositories.transaction_repository import SqliteTransactionRepository
from src.utils.page_base import BasePage

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
        # Ensure database is initialized
        init_db()
        super().__init__("總覽 (Overview)", "📊")
        
        # Initialize Services & Repositories (Init at composition root)
        # 初始化服務與存儲庫
        self.db_path = "data/portfolio.db" # Default path, should come from settings in ideal world
        self.transaction_repo = SqliteTransactionRepository()
        self.transaction_service = TransactionService(repository=self.transaction_repo)
        self.market_service = MarketDataService()
        
        # Analytics Engines
        self.calc = LeverageCalculator(db_path=self.db_path)
        self.roi_engine = ROIEngine(db_path=self.db_path)
        self.pnl_calc = PnLCalculator(db_path=self.db_path)
    
    def render(self):
        """
        Render dashboard content.
        渲染儀表板內容。
        """
        user_id = self.user['email']
        
        # Update daily snapshot for charts/history (Update on load)
        # 更新每日快照以供圖表/歷史紀錄使用
        update_daily_snapshot(self.db_path, user_id=user_id)

        # 1. Fetch Transactions (獲取交易紀錄)
        transactions_df = self.transaction_service.get_transactions(user_id)
        
        # 2. Identify Active Tickers (識別活躍股票)
        active_tickers = []
        if not transactions_df.empty:
            holdings = transactions_df.copy()
            # Buy (+), Sell (-)
            holdings['qty_signed'] = holdings.apply(lambda x: x['quantity'] if x['action'] == 'BUY' else -x['quantity'], axis=1)
            active_holdings = holdings.groupby('ticker')['qty_signed'].sum()
            # Filter holdings > threshold (avoid floating point zero issues)
            active_tickers = active_holdings[active_holdings > 0.0001].index.tolist()

        # 3. Fetch Real-time Prices (獲取即時價格)
        current_prices = {}
        
        @st.cache_data(ttl=300)
        def fetch_market_prices(tickers):
            # Helper to cache price fetch
            service = MarketDataService()
            return service.get_current_prices(tickers)

        if active_tickers:
            current_prices = fetch_market_prices(active_tickers)
            # Handle missing prices gracefully (display as 0, don't crash)

        # 4. Calculate & Display Metrics (計算並顯示指標)
        try:
            metrics = self.calc.calculate_metrics(current_prices, user_id=user_id)
            pnl_data = self.pnl_calc.calculate_breakdown(current_prices, user_id=user_id)
            roi = self.roi_engine.calculate_roi(metrics['nlv'], user_id=user_id)

            col1, col2, col3, col4 = st.columns(4)
            col1.metric("淨流動資產價值 (NLV)", f"${metrics['nlv']:,.2f}")
            col2.metric("現金餘額 (Cash Balance)", f"${metrics['cash_balance']:,.2f}")

            lev_ratio = metrics['leverage_ratio']
            lev_color = "normal"
            if lev_ratio >= 2.0: lev_color = "inverse" # High risk highlight
            col3.metric("槓桿比率 (Leverage Ratio)", f"{lev_ratio:.2f}x", delta_color=lev_color)
            col4.metric("總投資報酬率 (Total ROI)", f"{roi:.2f}%")

            st.markdown("---")
            c1, c2, c3 = st.columns(3)
            c1.metric("已實現損益 (Realized P&L)", f"${pnl_data['realized']:,.2f}", delta=f"${pnl_data['realized']:,.2f}")
            c2.metric("未實現損益 (Unrealized P&L)", f"${pnl_data['unrealized']:,.2f}", delta=f"${pnl_data['unrealized']:,.2f}")
            c3.metric("總損益 (Total P&L)", f"${pnl_data['total']:,.2f}", delta=f"${pnl_data['total']:,.2f}")

            if lev_ratio >= 2.0:
                st.error("⚠️ 危險警告: 槓桿比率過高！有追繳保證金風險 (Margin Call Risk)。")
            elif lev_ratio >= 1.5:
                st.warning("⚠️ 警告: 槓桿比率偏高 (Leverage Ratio is high)。")

        except Exception as e:
            st.error(f"計算指標時發生錯誤 (Error calculating metrics): {e}")

        # 5. Display Holdings (顯示持倉)
        st.subheader("當前持倉 (Current Positions)")

        try:
            if not transactions_df.empty:
                positions_df = transactions_df.copy()
                positions_df['qty_signed'] = positions_df.apply(lambda x: x['quantity'] if x['action'] == 'BUY' else -x['quantity'], axis=1)
                positions_grouped = positions_df.groupby('ticker')['qty_signed'].sum().reset_index()
                positions_df = positions_grouped[positions_grouped['qty_signed'] > 0.0001].rename(columns={'qty_signed': 'quantity'})

                if not positions_df.empty:
                    # Map prices
                    positions_df['current_price'] = positions_df['ticker'].map(current_prices).fillna(0)
                    positions_df['market_value'] = positions_df['quantity'] * positions_df['current_price']

                    display_df = positions_df.rename(columns={
                        'ticker': '股票代碼 (Ticker)',
                        'quantity': '數量 (Qty)',
                        'current_price': '當前價格 (Price)',
                        'market_value': '市值 (Market Value)'
                    })
                    st.dataframe(display_df.style.format({
                        "數量 (Qty)": "{:.4f}", 
                        "當前價格 (Price)": "{:.4f}", 
                        "市值 (Market Value)": "{:.4f}"
                    }), use_container_width=True)

                    st.subheader("資產配置 (Portfolio Allocation)")
                    
                    valid_pie_data = positions_df[positions_df['market_value'] > 0]
                    if not valid_pie_data.empty:
                        fig = px.pie(valid_pie_data, values='market_value', names='ticker', title='資產分佈 (Portfolio Allocation)')
                        st.plotly_chart(fig)
                    else:
                        st.info("無法顯示資產分佈圖 (市值皆為 0 或負值)")
                else:
                     st.info("尚無持倉紀錄 (No active positions found)。")
            else:
                st.info("尚無持倉紀錄 (No active positions found)。")

        except Exception as e:
            st.error(f"顯示持倉時發生錯誤 (Error displaying positions): {e}")


if __name__ == "__main__":
    DashboardPage().run()
