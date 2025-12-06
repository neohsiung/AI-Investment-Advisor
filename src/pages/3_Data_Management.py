import streamlit as st
import pandas as pd
from src.database import get_db_connection
from src.analytics import LeverageCalculator, SnapshotRecorder, update_daily_snapshot
from src.services.transaction_service import TransactionService
from src.ingestor import TradeIngestor
import os
from sqlalchemy import text
from tenacity import retry, stop_after_attempt, wait_fixed

def render_manual_entry_tab(st, service: TransactionService):
    st.subheader("新增交易 (Manual Entry)")
    
    with st.form("manual_trade_form"):
        col1, col2, col3 = st.columns(3)
        with col1:
            ticker = st.text_input("代號 (Ticker)", value="AAPL").upper()
            date_col = st.date_input("日期 (Date)")
        with col2:
            action = st.selectbox("動作 (Action)", ["BUY", "SELL", "DIVIDEND", "DEPOSIT", "WITHDRAW"])
            quantity = st.number_input("數量 (Quantity)", min_value=0.0, value=1.0, step=0.1)
        with col3:
            price = st.number_input("價格 (Price)", min_value=0.0, value=150.0)
            fees = st.number_input("手續費 (Fees)", min_value=0.0, value=0.0)
            
        submitted = st.form_submit_button("提交交易 (Submit Trade)")
        
        if submitted:
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
            st.dataframe(df.style.format({"quantity": "{:.4f}", "price": "{:.2f}", "amount": "{:.2f}"}), use_container_width=True)
            
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

def render_csv_import_tab(st, db_path):
    st.subheader("批次匯入 (CSV Import)")
    
    uploaded_file = st.file_uploader("上傳 CSV (Upload CSV)", type=["csv"])
    broker = st.selectbox("券商格式 (Broker Format)", ["Robinhood", "IBKR", "Simple"])
    
    if uploaded_file and st.button("開始匯入 (Start Import)"):
         # Save temp
         import os
         with open("temp.csv", "wb") as f:
             f.write(uploaded_file.getbuffer())
         
         try:
             ingestor = TradeIngestor(db_path)
             ingestor.ingest_csv("temp.csv", broker.lower())
             st.success("匯入成功！")
             os.remove("temp.csv")
             # Update snapshot
             update_daily_snapshot(db_path)
         except Exception as e:
             st.error(f"匯入失敗: {e}")

def render_data_browser(st, db_path):
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
        # Using f-string is safe here because we validated 'table' against the whitelist
        df = pd.read_sql(text(f"SELECT * FROM {table} ORDER BY 1 DESC LIMIT 100"), conn)
        st.dataframe(df, use_container_width=True)
    except Exception as e:
        st.error(f"Error: {e}")
    finally:
        conn.close()

def main():
    st.set_page_config(page_title="資料管理 | AI 投資顧問", layout="wide")
    st.title("資料管理 (Data Management)")
    
    db_path = st.sidebar.text_input("資料庫路徑 (Database Path)", "data/portfolio.db")
    service = TransactionService(db_path)
    
    tab1, tab2, tab3, tab4 = st.tabs(["手動輸入 (Manual Entry)", "CSV 匯入 (Import)", "交易紀錄 (Transactions)", "資料瀏覽 (Browser)"])
    
    with tab1:
        render_manual_entry_tab(st, service)
    
    with tab2:
        render_csv_import_tab(st, db_path)
        
    with tab3:
        render_transactions_tab(st, service)

    with tab4:
        render_data_browser(st, db_path)

if __name__ == "__main__":
    main()
