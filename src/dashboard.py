import streamlit as st
import pandas as pd
from src.database import get_db_connection
from src.analytics import LeverageCalculator, ROIEngine, update_daily_snapshot, PnLCalculator
import plotly.express as px
from src.market_data import MarketDataService

def main():
    st.set_page_config(page_title="總覽 | AI 投資顧問", layout="wide")

    st.title("AI 投資顧問總覽 (Overview)")

    # 側邊欄：設定與操作
    st.sidebar.header("設定 (Settings)")
    db_path = st.sidebar.text_input("資料庫路徑 (Database Path)", "data/portfolio.db")

    # 自動更新今日績效快照
    try:
        update_daily_snapshot(db_path)
    except Exception as e:
        st.warning(f"自動更新績效失敗 (Auto-update failed): {e}")

    # 初始化引擎
    calc = LeverageCalculator(db_path=db_path)
    roi_engine = ROIEngine(db_path=db_path)
    pnl_calc = PnLCalculator(db_path=db_path)

    # 2. 獲取真實市場數據
    market_service = MarketDataService()

    # 取得活躍持倉 Tickers
    conn = get_db_connection(db_path)
    try:
        active_tickers_df = pd.read_sql("SELECT ticker, SUM(CASE WHEN action='BUY' THEN quantity WHEN action='SELL' THEN -quantity ELSE 0 END) as quantity FROM transactions GROUP BY ticker HAVING quantity > 0.0001", conn)
    finally:
        conn.close()

    active_tickers = active_tickers_df['ticker'].tolist() if not active_tickers_df.empty else []

    # 獲取價格 (含 AI Fallback)
    current_prices = {}
    @st.cache_data(ttl=300)
    def fetch_market_prices(tickers):
        service = MarketDataService()
        return service.get_current_prices(tickers)

    if active_tickers:
        # 先嘗試批量獲取 (Cached)
        current_prices = fetch_market_prices(active_tickers)
        
        # 檢查是否有遺漏，若有則嘗試 AI Fallback
        for ticker in active_tickers:
            if ticker not in current_prices or current_prices[ticker] == 0:
                ai_data = market_service._fetch_from_llm(ticker)
                if ai_data:
                    current_prices[ticker] = ai_data.get('price', 0)

    # 1. 關鍵指標 (KPIs)
    try:
        metrics = calc.calculate_metrics(current_prices)
        pnl_data = pnl_calc.calculate_breakdown(current_prices)
        roi = roi_engine.calculate_roi(metrics['nlv'])
        
        # Row 1: NLV & Cash
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("淨流動資產價值 (NLV)", f"${metrics['nlv']:,.2f}")
        col2.metric("現金餘額 (Cash Balance)", f"${metrics['cash_balance']:,.2f}")
        
        lev_ratio = metrics['leverage_ratio']
        lev_color = "normal"
        if lev_ratio >= 2.0: lev_color = "inverse"
        col3.metric("槓桿比率 (Leverage Ratio)", f"{lev_ratio:.2f}x", delta_color=lev_color)
        col4.metric("總投資報酬率 (Total ROI)", f"{roi:.2f}%")

        # Row 2: PnL Breakdown
        st.markdown("---")
        c1, c2, c3 = st.columns(3)
        c1.metric("已實現損益 (Realized P&L)", f"${pnl_data['realized']:,.2f}", 
                  delta=f"${pnl_data['realized']:,.2f}")
        c2.metric("未實現損益 (Unrealized P&L)", f"${pnl_data['unrealized']:,.2f}", 
                  delta=f"${pnl_data['unrealized']:,.2f}")
        c3.metric("總損益 (Total P&L)", f"${pnl_data['total']:,.2f}", 
                  delta=f"${pnl_data['total']:,.2f}")

        # 警示
        if lev_ratio >= 2.0:
            st.error("⚠️ 危險警告: 槓桿比率過高！有追繳保證金風險 (Margin Call Risk)。")
        elif lev_ratio >= 1.5:
            st.warning("⚠️ 警告: 槓桿比率偏高 (Leverage Ratio is high)。")

    except Exception as e:
        st.error(f"計算指標時發生錯誤 (Error calculating metrics): {e}")

    # 2. 持倉明細
    st.subheader("當前持倉 (Current Positions)")
    conn = get_db_connection(db_path)
    try:
        positions_df = pd.read_sql("SELECT ticker, SUM(CASE WHEN action='BUY' THEN quantity WHEN action='SELL' THEN -quantity ELSE 0 END) as quantity FROM transactions GROUP BY ticker HAVING quantity != 0", conn)
    finally:
        conn.close()

    # 補上市價與市值
    if not positions_df.empty:
        positions_df['current_price'] = positions_df['ticker'].map(current_prices).fillna(0)
        positions_df['market_value'] = positions_df['quantity'] * positions_df['current_price']
        
        # Rename columns for display
        display_df = positions_df.rename(columns={
            'ticker': '股票代碼',
            'quantity': '數量',
            'current_price': '當前價格',
            'market_value': '市值'
        })
        st.dataframe(display_df)
        
        # 3. 資產分佈圖
        st.subheader("資產配置 (Portfolio Allocation)")
        fig = px.pie(positions_df, values='market_value', names='ticker', title='資產分佈 (Portfolio Allocation)')
        st.plotly_chart(fig)
    else:
        st.info("尚無持倉紀錄 (No active positions found)。")

if __name__ == "__main__":
    main()
