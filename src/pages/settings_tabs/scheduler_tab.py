import streamlit as st
import pandas as pd
import pytz
import time
from src.services.settings_service import SettingsService
from src.agents.engineer import SystemEngineerAgent
from src.utils.time_utils import get_timezone
from src.utils.components import saas_card_start, saas_card_end

def render_scheduler_tab(st, db_path):
    sys_settings_service = SettingsService(db_path, user_id='SYSTEM')
    engineer = SystemEngineerAgent()
    config = engineer.get_schedule_config()
    
    saas_card_start(title="Automation & Preferences", subtitle="統一配置系統時區與自動化分析排程", icon="🤖")
    
    # Common Timezones
    current_tz = sys_settings_service.get_setting("DISPLAY_TIMEZONE", "Asia/Taipei")
    common_timezones = ['Asia/Taipei', 'UTC', 'US/Eastern', 'US/Pacific', 'Europe/London', 'Asia/Tokyo']
    if current_tz not in common_timezones: common_timezones.append(current_tz)
    
    # Reverse Days Mapping
    days_map = {
        "monday": "週一 (Mon)", "tuesday": "週二 (Tue)", "wednesday": "週三 (Wed)",
        "thursday": "週四 (Thu)", "friday": "週五 (Fri)", "saturday": "週六 (Sat)", "sunday": "週日 (Sun)"
    }
    reverse_days_map = {v: k for k, v in days_map.items()}

    with st.form("unified_config_form"):
        # Top Row: Timezone
        c_tz1, c_tz2 = st.columns([2, 1])
        with c_tz1:
            all_tzs = common_timezones + [tz for tz in pytz.common_timezones if tz not in common_timezones]
            new_tz = st.selectbox("顯示時區 (System Timezone)", 
                                 options=all_tzs,
                                 index=all_tzs.index(current_tz) if current_tz in all_tzs else 0)
        with c_tz2:
            st.markdown('<div style="margin-top: 1.8rem;"></div>', unsafe_allow_html=True)
            st.caption(f"目前基準: **{current_tz}**")

        st.markdown('<hr style="margin: 0.75rem 0;">', unsafe_allow_html=True)

        # Middle Row: Daily & Weekly side-by-side
        col_left, col_right = st.columns(2)
        
        with col_left:
            st.markdown("##### 📅 每日分析 (Daily)")
            d_time_val = pd.to_datetime(config.get("schedule_daily", "09:00"), format="%H:%M").time()
            d_time = st.time_input("時間 (Daily Time)", value=d_time_val, label_visibility="collapsed")
            
            d_days_str = config.get("schedule_daily_days", "monday,tuesday,wednesday,thursday,friday")
            d_days = [d.strip() for d in d_days_str.split(",") if d.strip()]
            d_options = [days_map.get(d, d) for d in d_days if d in days_map]
            
            daily_days_selected = st.multiselect("執行日 (Days)", options=list(days_map.values()), default=d_options)
            
        with col_right:
            st.markdown("##### 📊 每週報告 (Weekly)")
            w_time_val = pd.to_datetime(config.get("schedule_weekly", "09:00"), format="%H:%M").time()
            weekly_time = st.time_input("時間 (Weekly Time)", value=w_time_val, label_visibility="collapsed")
            
            w_day = config.get("schedule_weekly_day", "saturday")
            weekly_day = st.selectbox("每週報告日 (Weekly Day)", options=list(days_map.keys()), format_func=lambda x: days_map[x], index=list(days_map.keys()).index(w_day) if w_day in days_map else 5)

        st.markdown('<div style="margin-top: 0.5rem;"></div>', unsafe_allow_html=True)
        
        if st.form_submit_button("儲存所有設定 (Save All Preferences)", type="primary", use_container_width=True):
            try:
                # 1. Update Timezone
                if new_tz != current_tz:
                    sys_settings_service.save_setting('DISPLAY_TIMEZONE', new_tz)
                
                # 2. Update Schedule
                selected_keys = [reverse_days_map[d] for d in daily_days_selected]
                order_lookup = list(days_map.keys())
                selected_keys.sort(key=lambda x: order_lookup.index(x) if x in order_lookup else 99)
                
                engineer.set_schedule_config(
                    daily_time=d_time.strftime("%H:%M"), 
                    weekly_time=weekly_time.strftime("%H:%M"), 
                    weekly_day=weekly_day,
                    daily_days=selected_keys
                )
                
                # Signal Reload
                sys_settings_service.save_setting('scheduler_reload_signal', 'true')
                
                st.success("設定已更新！")
                time.sleep(1)
                st.rerun()
            except Exception as e:
                st.error(f"更新失敗: {e}")
                
    saas_card_end()

    saas_card_start(title="Operational Logs", subtitle="查看 Scheduler 最近 50 筆執行狀態與錯誤日誌", icon="📋")

    # Scheduler logs via Service
    from src.services.scheduler_service import SchedulerService
    scheduler_service = SchedulerService()
    try:
        logs_df = scheduler_service.get_execution_logs(limit=50)
        
        user_tz = get_timezone()
        
        # Helper to safely localize
        def localize_ts(ts):
            try:
                dt = pd.to_datetime(ts)
                if dt.tzinfo is not None:
                     return dt.astimezone(user_tz)
                return pytz.utc.localize(dt).astimezone(user_tz)
            except:
                return ts

        logs_df['timestamp'] = logs_df['timestamp'].apply(localize_ts)
        logs_df['timestamp'] = logs_df['timestamp'].dt.strftime('%Y-%m-%d %H:%M:%S')
        
        st.dataframe(logs_df, use_container_width=True)
    except Exception as e:
        st.info("尚無排程紀錄。")

    if st.button("重新整理 (Refresh Logs)"):
        st.rerun()
    saas_card_end()
