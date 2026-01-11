import streamlit as st
from src.utils.ui import render_theme_switcher
from src.utils.components import saas_card_start, saas_card_end

def render_appearance_tab(st):
    saas_card_start(title="Visual Identity", subtitle="切換系統佈景主題及存取介面開發手冊", icon="🎨")
    st.markdown("### 主題切換 (Theme Switching)")
    render_theme_switcher(key_suffix="settings_page")
    
    st.divider()
    st.markdown("### 快訊與指南 (Quick Links)")
    st.page_link("pages/_UI_Styleguide.py", label="介面開發組件手冊 (Interface Guide)", icon="🎨")
    st.caption("查看系統支援的所有 SaaS UI 組件、配色與排版規範。")
    saas_card_end()
