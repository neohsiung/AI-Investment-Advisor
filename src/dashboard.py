import streamlit as st
import pandas as pd
import os
from src.data.database import get_db_connection, init_db
from src.analytics import LeverageCalculator, ROIEngine, update_daily_snapshot, PnLCalculator
import plotly.express as px
from src.market_data import MarketDataService
from src.auth import auth_manager

def main():
    st.set_page_config(page_title="總覽 | AI 投資顧問", layout="wide")

    # Initialize DB (Safe to call repeatedly, checks IF NOT EXISTS)
    # Use default path or env var logic handled inside init_db
    # Note: We use the default path here, if user changes sidebar input later, it might need re-init,
    # but usually `data/portfolio.db` is the target.
    init_db()

    init_db()

    # --- UI Styling (SaaS Look) ---
    from src.utils.ui import load_custom_css
    load_custom_css()
    # ------------------------------

    # --- Authentication Check ---

    # --- Authentication Check ---
    # --- Authentication Check ---
    # Check if client_secret.json exists (simplistic check for better UX)
    import os

    # Check if client_secret.json exists OR if we have the content in Env Vars
    has_secret_file = os.path.exists(os.getenv('GOOGLE_CLIENT_SECRET_PATH', 'client_secret.json'))
    has_secret_env = os.getenv('GOOGLE_CLIENT_SECRET_JSON') is not None or os.getenv('client_secret.json') is not None

    if not has_secret_file and not has_secret_env:
        st.error("⚠️ 找不到 Google OAuth 設定檔 (`client_secret.json`)。")
        st.markdown("""
        ### 如何解決 (How to fix):
        本系統需要 Google OAuth 憑證才能運作。

        請參考 Wiki 中的詳細設定指南：
        👉 **[Google-OAuth-Setup](wiki/Google-OAuth-Setup.md)**

        **簡易步驟**:
        1. 按照指南從 Google Cloud Console 下載憑證 JSON 檔。
        2. 將檔案重新命名為 `client_secret.json`。
        3. 將該檔案放置於此專案的**根目錄**下。
        """)
        st.stop()

    auth_manager.check_login() # Initialize check

    if not auth_manager.get_current_user():
        st.title("登入 (Login)")
        st.write("請使用 Google 帳號登入以存取您的投資顧問儀表板。")
        auth_manager.login()
        st.stop()

    user = auth_manager.get_current_user()
    user_id = user['email'] # Using email as user_id for simplicity as per migration logic

    # Logout Button in Sidebar
    with st.sidebar:
        st.write(f"Logged in as: **{user['name']}**")
        if st.button("Logout"):
            auth_manager.logout()
        st.divider()

    st.title("AI 投資顧問總覽 (Overview)")

    # 側邊欄：設定與操作
    st.sidebar.header("設定 (Settings)")
    db_path = st.sidebar.text_input("資料庫路徑 (Database Path)", "data/portfolio.db")

    # 自動更新今日績效快照
    try:
        update_daily_snapshot(db_path, user_id=user_id)
    except Exception as e:
        st.warning(f"自動更新績效失敗 (Auto-update failed): {e}")

    # 初始化引擎
    calc = LeverageCalculator(db_path=db_path)
    roi_engine = ROIEngine(db_path=db_path)
    pnl_calc = PnLCalculator(db_path=db_path)

    # 初始化服務與 Repository (Initialize Services)
    # 使用 TransactionService 來處理所有與交易相關的資料存取，實現 Clean Architecture
    # Use TransactionService for all transaction-related data access
    from src.services.transaction_service import TransactionService
    from src.repositories.transaction_repository import SqliteTransactionRepository

    # 依賴注入 (Dependency Injection)
    transaction_repo = SqliteTransactionRepository()
    transaction_service = TransactionService(repository=transaction_repo)

    # 2. 獲取真實市場數據 (Fetch Real Market Data)
    market_service = MarketDataService()

    # 取得活躍持倉 Tickers (Filtered by User)
    # 改用 Service 層獲取，避免直接 SQL 操作
    transactions_df = transaction_service.get_transactions(user_id)

    # 計算活躍持倉 (Calculate Active Positions)
    # 邏輯: 買入為正，賣出為負，加總後大於 0 代表持有
    if not transactions_df.empty:
        # 重整資料以計算持倉 (Reshape data to calculate holdings)
        holdings = transactions_df.copy()
        holdings['qty_signed'] = holdings.apply(lambda x: x['quantity'] if x['action'] == 'BUY' else -x['quantity'], axis=1)
        active_holdings = holdings.groupby('ticker')['qty_signed'].sum()
        active_tickers = active_holdings[active_holdings > 0.0001].index.tolist()
    else:
        active_tickers = []

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
                # Fallback needs improvement to avoid frequent calls, but kept logic same
                ai_data = market_service._fetch_from_llm(ticker)
                if ai_data:
                    current_prices[ticker] = ai_data.get('price', 0)

    # 1. 關鍵指標 (KPIs)
    try:
        metrics = calc.calculate_metrics(current_prices, user_id=user_id)
        pnl_data = pnl_calc.calculate_breakdown(current_prices, user_id=user_id)
        roi = roi_engine.calculate_roi(metrics['nlv'], user_id=user_id)

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

    # 2. 持倉明細 (Current Positions)
    st.subheader("當前持倉 (Current Positions)")

    # 使用與上方相同的邏輯計算持倉 DataFrame
    if not transactions_df.empty:
        # Group by Ticker to get total quantity
        positions_df = transactions_df.copy()
        positions_df['qty_signed'] = positions_df.apply(lambda x: x['quantity'] if x['action'] == 'BUY' else -x['quantity'], axis=1)
        positions_grouped = positions_df.groupby('ticker')['qty_signed'].sum().reset_index()
        positions_df = positions_grouped[positions_grouped['qty_signed'] > 0.0001].rename(columns={'qty_signed': 'quantity'})
    else:
        positions_df = pd.DataFrame(columns=['ticker', 'quantity'])

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
        st.dataframe(display_df.style.format({"數量": "{:.4f}", "當前價格": "{:.4f}", "市值": "{:.4f}"}), use_container_width=True)

        # 3. 資產分佈圖
        st.subheader("資產配置 (Portfolio Allocation)")
        fig = px.pie(positions_df, values='market_value', names='ticker', title='資產分佈 (Portfolio Allocation)')
        st.plotly_chart(fig)
    else:
        st.info("尚無持倉紀錄 (No active positions found)。")

if __name__ == "__main__":
    main()
