from __future__ import annotations
import streamlit as st
from src.services.transaction_service import TransactionService
from src.utils.page_base import BasePage
from src.utils.components import saas_metric, saas_card_start, saas_card_end, saas_section_header, saas_alert


# Helper functions for tabs
def render_manual_entry_tab(st, service: TransactionService):
    saas_card_start(title="Transaction Input", subtitle="手動建立交易紀錄或調整持倉", icon="📝")
    
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
             st.error("請輸入代號 (Ticker)")
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
    saas_card_end()

def render_transactions_tab(st, service: TransactionService):
    saas_card_start(title="Audit Trail", subtitle="歷史成交紀錄與管理", icon="📜")

    df = service.get_transactions()

    if df is not None:
        if not df.empty:
            df['Delete'] = False
            
            column_config = {
                "Delete": st.column_config.CheckboxColumn(
                    "刪除? (Delete)",
                    help="勾選以刪除此筆交易",
                    default=False,
                ),
                "quantity": st.column_config.NumberColumn(format="%.4f"),
                "price": st.column_config.NumberColumn(format="%.4f"),
                "amount": st.column_config.NumberColumn(format="%.4f"),
                "id": None,
            }

            edited_df = st.data_editor(
                df,
                column_config=column_config,
                disabled=["trade_date", "ticker", "action", "quantity", "price", "fees", "amount"],
                hide_index=True,
                use_container_width=True,
                key="data_editor_transactions"
            )

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
        saas_card_end()
    else:
        st.error("無法讀取交易紀錄。")

def render_csv_import_tab(st, db_path, user_id):
    saas_card_start(title="Batch Integration", subtitle="自動化匯入券商匯出資料", icon="📂")

    uploaded_file = st.file_uploader("上傳 CSV (Upload CSV)", type=["csv"])

    broker_options = {
        "Robinhood": "Robinhood (羅賓漢)",
        "IBKR": "IBKR (盈透證券)",
        "Simple": "Simple (簡易格式)"
    }
    broker_key = st.selectbox("券商格式 (Broker Format)", options=list(broker_options.keys()), format_func=lambda x: broker_options[x])
    broker = broker_key

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
    saas_card_end()

def render_data_browser(st, db_path, user_id):
    from src.repositories.data_repository import SqliteDataRepository
    
    repo = SqliteDataRepository(db_path)
    saas_card_start(title="System Inspector", subtitle="直接瀏覽資料庫底層數據", icon="🔍")
    table = st.selectbox("選擇資料表", ["transactions", "daily_snapshots", "cash_flows", "positions", "reports", "settings"])

    try:
        df = repo.get_table_preview(table, user_id, limit=100)
        st.dataframe(df, use_container_width=True)
    except Exception as e:
        st.error(f"Error reading table (Access Denied or Schema Mismatch): {e}")
    
    saas_card_end()


class DataManagementPage(BasePage):
    """Data management page"""
    
    def __init__(self):
        super().__init__("資料管理 (Data Management)", "💾")
    
    def render(self):
        """Render data management content"""
        user_id = self.user['email']
        db_path = self.db_path
        user_name = self.user['name']
        
        # Update title with user name

        
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
    DataManagementPage().run()
