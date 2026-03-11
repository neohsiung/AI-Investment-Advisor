import streamlit as st
import json
from src.services.settings_service import SettingsService

def render_data_sources_tab(st, settings_service, user_id):
    """
    Renders the Data Source Management tab.
    數據源管理分頁：提供 15+ 資料源的開關與參數設定。
    """
    st.header("數據源矩陣管理 (Data Source Matrix)")
    st.markdown("---")

    # Define Source Groups by Coverage/Priority
    from src.config.data_source_matrix_config import DATA_SOURCE_GROUPS
    source_groups = DATA_SOURCE_GROUPS

    # Load all settings once
    settings = settings_service.get_all_settings()

    # Iterate through groups with collapsibles
    for group_name, group_data in source_groups.items():
        with st.expander(f"📁 {group_name}", expanded=(group_data['priority'] <= 2)):
            for source in group_data['sources']:
                sid = source['id']
                col1, col2 = st.columns([1, 4])
                
                with col1:
                    # Toggle Enable/Disable
                    # v4.3.4: Use real boolean values for DB best practice
                    current_enabled = settings.get(f"source_{sid}_enabled", False)
                    is_enabled_bool = str(current_enabled).lower() == "true" if not isinstance(current_enabled, bool) else current_enabled
                    
                    is_enabled = st.toggle(
                        "啟用", 
                        key=f"enabled_{sid}", 
                        value=is_enabled_bool,
                        help=f"是否開啟 {source['name']} 的自動輪詢或監控"
                    )
                
                with col2:
                    st.write(f"**{source['name']}**")
                    if 'url' in source:
                        st.markdown(f"🔗 [官方網站與設定 (Official Website)]({source['url']})")
                    st.caption(source['desc'])
                
                # If enabled, show config fields
                if is_enabled:
                    scol1, scol2 = st.columns([1, 1])
                    for i, (fname, fmeta) in enumerate(source['fields'].items()):
                        key = f"source_{sid}_{fname}"
                        val = settings.get(key, fmeta.get('default', ""))
                        
                        target_col = scol1 if i % 2 == 0 else scol2
                        with target_col:
                            if fmeta.get('type') == 'password':
                                new_val = st.text_input(fmeta['label'], value=val, type="password", key=f"input_{key}", help=fmeta.get('help', ""))
                            else:
                                new_val = st.text_input(fmeta['label'], value=val, key=f"input_{key}", help=fmeta.get('help', ""))
                            
                            if new_val != val:
                                settings_service.save_setting(key, new_val)
                                # Signal Reload (Use real boolean True)
                                settings_service.save_setting('scheduler_reload_signal', True)
                
                # Save toggle state if changed (Use real boolean)
                if is_enabled != is_enabled_bool:
                    settings_service.save_setting(f"source_{sid}_enabled", is_enabled)
                    # Signal Reload (Use real boolean True)
                    settings_service.save_setting('scheduler_reload_signal', True)
                
                st.divider()

    st.success("數據源設定已即時同步至資料庫。")
