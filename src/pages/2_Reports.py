import streamlit as st
import pandas as pd
from src.database import get_db_connection

st.set_page_config(page_title="分析報告 | AI 投資顧問", layout="wide")

st.title("投資顧問報告 (Investment Advisory Reports)")

# Sidebar 設定
st.sidebar.header("設定 (Settings)")
db_path = st.sidebar.text_input("資料庫路徑 (Database Path)", "data/portfolio.db")

conn = get_db_connection(db_path)
reports_df = pd.read_sql("SELECT date, summary, content FROM reports ORDER BY date DESC", conn)

if not reports_df.empty:
    selected_report_date = st.selectbox("選擇報告日期 (Select Report Date)", reports_df['date'].unique())
    report_content = reports_df[reports_df['date'] == selected_report_date]['content'].values[0]
    st.markdown("---")
    st.markdown(report_content)
else:
    st.info("尚無報告可供檢視。請執行 workflow.py 生成報告。(No reports available yet.)")

conn.close()
