import streamlit as st
import pandas as pd
from src.database import get_db_connection

st.set_page_config(page_title="數據管理 | AI 投資顧問", layout="wide")

st.title("數據管理 (Data Management)")

# Sidebar 設定
st.sidebar.header("設定 (Settings)")
db_path = st.sidebar.text_input("資料庫路徑 (Database Path)", "data/portfolio.db")

from src.analytics import LeverageCalculator, SnapshotRecorder, update_daily_snapshot

# 移除本地定義的 update_daily_snapshot，直接使用 import 的版本

tab1, tab2, tab3 = st.tabs(["CSV 匯入 (Import)", "手動輸入 (Manual Entry)", "近期交易 (Recent Transactions)"])

with tab1:
    st.subheader("從 CSV 匯入交易 (Import Trades from CSV)")
    broker = st.selectbox("選擇券商 (Select Broker)", ["Robinhood", "IBKR", "Simple"])
    uploaded_file = st.file_uploader("選擇 CSV 檔案 (Choose a CSV file)", type="csv")
    
    if uploaded_file is not None:
        if st.button("匯入 CSV (Ingest CSV)"):
            with st.spinner('處理中... (Processing...)'):
                try:
                    # Save uploaded file temporarily
                    import os
                    temp_path = f"data/temp_{uploaded_file.name}"
                    with open(temp_path, "wb") as f:
                        f.write(uploaded_file.getbuffer())
                    
                    # Ingest
                    from src.ingestor import TradeIngestor
                    ingestor = TradeIngestor(db_path=db_path)
                    ingestor.ingest_csv(temp_path, broker=broker)
                    
                    # Update Snapshot
                    update_daily_snapshot(db_path)
                    
                    st.success(f"成功匯入 {uploaded_file.name} (格式: {broker})")
                    
                    # Clean up
                    os.remove(temp_path)
                    
                    # Rerun to update data
                    st.rerun()
                except Exception as e:
                    st.error(f"匯入失敗 (Error ingesting CSV): {e}")

with tab2:
    st.subheader("手動交易輸入 (Manual Trade Entry)")
    with st.form("manual_trade_form"):
        col1, col2 = st.columns(2)
        ticker = col1.text_input("股票代碼 (Ticker, e.g., AAPL)").upper()
        date = col2.date_input("交易日期 (Trade Date)")
        
        col3, col4, col5 = st.columns(3)
        action = col3.selectbox("動作 (Action)", ["BUY", "SELL"])
        quantity = col4.number_input("數量 (Quantity)", min_value=0.01, step=0.01)
        price = col5.number_input("價格 (Price)", min_value=0.01, step=0.01)
        fees = st.number_input("手續費 (Fees)", min_value=0.0, step=0.01, value=0.0)
        
        submitted = st.form_submit_button("新增交易 (Add Trade)")
        
        if submitted:
            if not ticker or quantity <= 0 or price <= 0:
                st.error("請正確填寫所有必填欄位 (Please fill in all required fields correctly).")
            else:
                with st.spinner('處理中... (Processing...)'):
                    try:
                        from src.ingestor import TradeIngestor
                        ingestor = TradeIngestor(db_path=db_path)
                        # Convert date to string
                        date_str = date.strftime("%Y-%m-%d")
                        ingestor.ingest_manual_trade(ticker, date_str, action, quantity, price, fees)
                        
                        # Update Snapshot
                        update_daily_snapshot(db_path)
                        
                        st.success(f"已新增交易: {action} {quantity} {ticker} @ {price}")
                        st.rerun()
                    except Exception as e:
                        st.error(f"新增失敗 (Error adding trade): {e}")

with tab3:
    st.subheader("近期交易紀錄 (Recent Transactions)")
    conn = get_db_connection(db_path)
    # Include ID for deletion
    transactions_df = pd.read_sql("SELECT id, date(trade_date) as date, ticker, action, quantity, price, amount FROM transactions ORDER BY trade_date DESC LIMIT 20", conn)
    
    if not transactions_df.empty:
        # Header
        h1, h2, h3, h4, h5, h6, h7 = st.columns([2, 2, 2, 2, 2, 2, 1])
        h1.markdown("**日期 (Date)**")
        h2.markdown("**代碼 (Ticker)**")
        h3.markdown("**動作 (Action)**")
        h4.markdown("**數量 (Qty)**")
        h5.markdown("**價格 (Price)**")
        h6.markdown("**金額 (Amount)**")
        h7.markdown("**操作**")
        
        for index, row in transactions_df.iterrows():
            c1, c2, c3, c4, c5, c6, c7 = st.columns([2, 2, 2, 2, 2, 2, 1])
            c1.write(row['date'])
            c2.write(row['ticker'])
            c3.write(row['action'])
            c4.write(f"{row['quantity']:.4f}")
            c5.write(f"${row['price']:.2f}")
            c6.write(f"${row['amount']:.2f}")
            
            if c7.button("刪除", key=f"del_{row['id']}", help="刪除此筆交易"):
                with st.spinner('刪除中... (Deleting...)'):
                    try:
                        del_conn = get_db_connection(db_path)
                        del_conn.execute("DELETE FROM transactions WHERE id = ?", (row['id'],))
                        del_conn.commit()
                        del_conn.close()
                        
                        # Update Snapshot
                        update_daily_snapshot(db_path)
                        
                        st.success("交易已刪除 (Transaction deleted)")
                        st.rerun()
                    except Exception as e:
                        st.error(f"刪除失敗: {e}")
    else:
        st.info("尚無交易紀錄 (No transactions found).")
        
    conn.close()
