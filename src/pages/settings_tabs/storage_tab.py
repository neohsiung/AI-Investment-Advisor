import streamlit as st
from src.utils.components import saas_card_start, saas_card_end

def render_storage_tab(st, db_path):
    saas_card_start(title="Data Storage", subtitle="管理系統本地資料庫路徑與存儲設定", icon="💾")
    st.markdown("### 資料庫配置 (Database Configuration)")
    st.info(f"當前使用的資料庫路徑為：`{db_path}`")
    new_db_path = st.text_input("修改資料庫路徑 (Database Path)", value=db_path, key="storage_db_path_input")
    if new_db_path != db_path:
        st.warning("變更路徑可能需要重啟應用程式以生效。")
    saas_card_end()
