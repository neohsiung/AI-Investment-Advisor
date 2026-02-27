import streamlit as st
import pandas as pd
import pytz
from src.services.settings_service import SettingsService
from src.utils.components import saas_card_start, saas_card_end
from src.utils.time_utils import get_timezone

def render_optimization_history_tab(st, db_path, user_id):
    saas_card_start(title="Prompt Meta-Learning", subtitle="追蹤 Engineer Agent 對系統 Prompt 的迭代優化軌跡", icon="✨")

    settings_service = SettingsService(db_path, user_id=user_id)
    
    try:
        history_df = settings_service.get_prompt_history(user_id)

        if history_df.empty:
            st.info("尚無優化紀錄。")
        else:
            user_tz = get_timezone()
            for _, row in history_df.iterrows():
                # Convert History Timestamp
                ts_str = row['timestamp']
                try:
                    dt = pd.to_datetime(ts_str)
                    if dt.tzinfo is not None:
                         dt_final = dt.astimezone(user_tz)
                    else:
                         dt_final = pytz.utc.localize(dt).astimezone(user_tz)
                    dt_display = dt_final.strftime('%Y-%m-%d %H:%M:%S')
                except:
                    dt_display = ts_str

                with st.expander(f"{dt_display} - {row['target_agent']}"):
                    st.caption(f"**Reason:** {row['reason']}")
                    st.text("Prompt Diff:")
                    st.code(row['diff_content'], language="diff")
    except Exception as e:
        # If schema mismatch or first run
        st.warning(f"讀取紀錄失敗 (可能是新表結構尚未初始化): {e}")
    saas_card_end()
