import streamlit as st
import pandas as pd
from src.data.database import get_db_connection
from src.analytics import LeverageCalculator, SnapshotRecorder, update_daily_snapshot
from src.services.transaction_service import TransactionService
from src.data.ingestor import TradeIngestor
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
            # Add selection column for deletion
            df['Delete'] = False
            
            # Configure columns
            column_config = {
                "Delete": st.column_config.CheckboxColumn(
                    "刪除? (Delete)",
                    help="勾選以刪除此筆交易",
                    default=False,
                ),
                "quantity": st.column_config.NumberColumn(format="%.4f"),
                "price": st.column_config.NumberColumn(format="%.4f"),
                "amount": st.column_config.NumberColumn(format="%.4f"),
                "id": None, # Hide ID
            }

            # Editable Dataframe
            edited_df = st.data_editor(
                df,
                column_config=column_config,
                disabled=["trade_date", "ticker", "action", "quantity", "price", "fees", "amount"],
                hide_index=True,
                use_container_width=True,
                key="data_editor_transactions"
            )

            # Delete Action
            to_delete = edited_df[edited_df['Delete'] == True]
            
            if not to_delete.empty:
                st.warning(f"已選擇 {len(to_delete)} 筆交易")
                if st.button(f"確認刪除 {len(to_delete)} 筆資料 (Confirm Delete)", type="primary"):
                    success_count = 0
                    fail_count = 0
                    
                    for _, row in to_delete.iterrows():
                        success, _ = service.delete_transaction(row['id'])
                        if success:
                            success_count += 1
                        else:
                            fail_count += 1
                    
                    if success_count > 0:
                        st.success(f"成功刪除 {success_count} 筆交易")
                    if fail_count > 0:
                        st.error(f"刪除失敗 {fail_count} 筆")
                    
                    if success_count > 0:
                        st.rerun()
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

    # Template Download
    if broker == "Simple":
        try:
            with open("data/template_simple.csv", "r") as f:
                template_data = f.read()
            st.download_button(
                label="📥 下載匯入範本 (Download Template)",
                data=template_data,
                file_name="import_template.csv",
                mime="text/csv",
                help="下載簡易格式的 CSV 範本以供參考"
            )
        except Exception as e:
            st.error(f"無法讀取範本檔案: {e}")

    if uploaded_file and st.button("開始匯入 (Start Import)"):
         try:
             from src.services.ingestion_service import IngestionService
             ingestion_service = IngestionService(db_path, user_id=user_id)
             
             success, msg = ingestion_service.process_csv_upload(uploaded_file, broker.lower())
             
             if success:
                 st.success(msg)
             else:
                 st.error(msg)
         except Exception as e:
             st.error(f"System Error: {e}")

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
