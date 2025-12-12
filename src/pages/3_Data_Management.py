import streamlit as st
import pandas as pd
from src.database import get_db_connection
from src.analytics import LeverageCalculator, SnapshotRecorder, update_daily_snapshot
from src.services.transaction_service import TransactionService
from src.ingestor import TradeIngestor
import os
from sqlalchemy import text
from tenacity import retry, stop_after_attempt, wait_fixed
from src.auth import auth_manager

def render_manual_entry_tab(st, service: TransactionService):
    st.subheader("新增交易 (Manual Entry)")

    st.radio("輸入模式 (Trade Mode)", ["依數量 (By Quantity)", "依槓桿 (By Leverage)"], key="trade_mode", horizontal=True)

    col1, col2, col3 = st.columns(3)

    with col1:
        ticker = st.text_input("代號 (Ticker)", value="AAPL").upper()
        date_col = st.date_input("日期 (Date)")

    with col2:
        action_options = {
            "BUY": "BUY (買入)",
            "SELL": "SELL (賣出)",
            "DIVIDEND": "DIVIDEND (股息)",
            "DEPOSIT": "DEPOSIT (入金)",
            "WITHDRAW": "WITHDRAW (出金)"
        }
        action_key = st.selectbox("動作 (Action)", options=list(action_options.keys()), format_func=lambda x: action_options[x])
        action = action_key

        # Dynamic Input based on Mode
        if st.session_state.get("trade_mode") == "依槓桿 (By Leverage)":
            principal = st.number_input("本金 (Margin/Principal)", min_value=0.0, value=1000.0, step=100.0)
            leverage = st.number_input("槓桿倍數 (Leverage)", min_value=1.0, value=1.0, step=0.1)
            # Placeholder for quantity, will be calculated later
            quantity = 0.0
        else:
            quantity_input = st.number_input("數量 (Quantity)", min_value=0.0, value=1.0, step=0.0001, format="%.4f")
            quantity = quantity_input

    with col3:
        price = st.number_input("價格 (Price)", min_value=0.0, value=150.0, step=0.0001, format="%.4f")
        fees = st.number_input("手續費 (Fees)", min_value=0.0, value=0.0, step=0.0001, format="%.4f")

    # Calculation Logic
    if st.session_state.get("trade_mode") == "依槓桿 (By Leverage)" and price > 0:
        total_buying_power = principal * leverage
        quantity_calced = total_buying_power / price
        quantity = quantity_calced
        st.info(f"📊 計算結果: 投入 ${principal:,.2f} x {leverage}倍 = 總購買力 ${total_buying_power:,.2f} (約 {quantity:.4f} 股)")

    if st.button("提交交易 (Submit Trade)", type="primary"):
        if not ticker:
             st.error("請輸入代號 (Ticker is required)")
        elif quantity <= 0 and action in ['BUY', 'SELL']:
             st.error("數量必須大於 0")
        elif price < 0:
             st.error("價格不能為負數")
        else:
             date_str = date_col.strftime("%Y-%m-%d")
             success, msg = service.add_manual_trade(ticker, date_str, action, quantity, price, fees)
             if success:
                 st.success(msg)
             else:
                 st.error(msg)

def render_transactions_tab(st, service: TransactionService):
    st.subheader("交易紀錄 (Transaction History)")

    df = service.get_transactions()

    if df is not None:
        if not df.empty:
            # Display recent transactions
            st.dataframe(df.style.format({"quantity": "{:.4f}", "price": "{:.4f}", "amount": "{:.4f}"}), use_container_width=True)

            # Delete functionality
            st.markdown("### 刪除交易 (Delete Transaction)")

            with st.form("delete_trans_form"):

                # Show last 10 for quick delete selection or text input
                options = [(row['id'], f"{row['trade_date']} - {row['ticker']} {row['action']} {row['quantity']} @ {row['price']}")
                           for _, row in df.head(20).iterrows()]

                selected_id = st.selectbox("選擇要刪除的交易 (Select to Delete)", options=options, format_func=lambda x: x[1])

                if st.form_submit_button("刪除 (Delete)"):
                    if selected_id:
                        trans_id = selected_id[0]
                        success, msg = service.delete_transaction(trans_id)
                        if success:
                            st.success(msg)
                            st.rerun()
                        else:
                            st.error(msg)
        else:
             st.info("尚無交易紀錄。")
    else:
        st.error("無法讀取交易紀錄。")

def render_csv_import_tab(st, db_path, user_id):
    st.subheader("批次匯入 (CSV Import)")

    uploaded_file = st.file_uploader("上傳 CSV (Upload CSV)", type=["csv"])

    broker_options = {
        "Robinhood": "Robinhood (羅賓漢)",
        "IBKR": "IBKR (盈透證券)",
        "Simple": "Simple (簡易格式)"
    }
    broker_key = st.selectbox("券商格式 (Broker Format)", options=list(broker_options.keys()), format_func=lambda x: broker_options[x])
    broker = broker_key

    if uploaded_file and st.button("開始匯入 (Start Import)"):
         # Save temp
         import os
         with open("temp.csv", "wb") as f:
             f.write(uploaded_file.getbuffer())

         try:
             ingestor = TradeIngestor(db_path)
             # Pass user_id to ingestor
             ingestor.ingest_csv("temp.csv", broker.lower(), user_id=user_id)
             st.success("匯入成功！")
             os.remove("temp.csv")
             # Update snapshot
             update_daily_snapshot(db_path, user_id=user_id)
         except Exception as e:
             st.error(f"匯入失敗: {e}")

def render_data_browser(st, db_path, user_id):
    # Data Browser Logic using direct SQL or Service
    # To be clean, let's keep direct SQL here for read-only debug or add to service
    st.subheader("資料庫瀏覽 (Data Browser)")
    table = st.selectbox("選擇資料表", ["transactions", "daily_snapshots", "cash_flows", "positions", "reports", "settings"])

    # Whitelist validation for table name to prevent SQL Injection
    allowed_tables = ["transactions", "daily_snapshots", "cash_flows", "positions", "reports", "settings", "prompt_history"]
    if table not in allowed_tables:
        st.error("Invalid table selected.")
        return

    conn = get_db_connection(db_path)
    try:
        # Filter by user_id
        # Need to check if table has user_id, but per our migration, they all do (except scheduler_logs which is global?)

        # Check if table has user_id column logic or just try catch?
        # Pragmatic: all user tables have user_id.
        # Using f-string is safe here because we validated 'table' against the whitelist
        df = pd.read_sql(text(f"SELECT * FROM {table} WHERE user_id = :uid ORDER BY 1 DESC LIMIT 100"), conn, params={"uid": user_id}) # nosec B608
        st.dataframe(df, use_container_width=True)
    except Exception as e:
        # Fallback if table doesn't have user_id (e.g. maybe some system table)
        # But we want to isolate data, so better fail or show empty if no user_id column
        st.error(f"Error reading table (Access Denied or Schema Mismatch): {e}")
    finally:
        conn.close()

def main():
    st.set_page_config(page_title="資料管理 | AI 投資顧問", layout="wide")

    if not auth_manager.check_login():
        st.warning("請先登入")
        return

    user = auth_manager.get_current_user()
    user_id = user['email']

    st.title(f"資料管理 (Data Management) - {user['name']}")

    db_path = st.sidebar.text_input("資料庫路徑 (Database Path)", "data/portfolio.db")

    # Pass user_id to service
    service = TransactionService(db_path, user_id=user_id)

    tab1, tab2, tab3, tab4 = st.tabs(["手動輸入 (Manual Entry)", "CSV 匯入 (Import)", "交易紀錄 (Transactions)", "資料瀏覽 (Browser)"])

    with tab1:
        render_manual_entry_tab(st, service)

    with tab2:
        render_csv_import_tab(st, db_path, user_id)

    with tab3:
        render_transactions_tab(st, service)

    with tab4:
        render_data_browser(st, db_path, user_id)

if __name__ == "__main__":
    main()
