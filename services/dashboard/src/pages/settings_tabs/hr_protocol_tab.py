import streamlit as st
from src.services.hr_service import HRService
from src.utils.components import saas_card_start, saas_card_end

def render_hr_protocol_tab(st):
    saas_card_start(title="Agent Health Monitor", subtitle="監控 Agent 活躍度與系統健康狀態 (HR 協議)", icon="🩺")
    
    hr_service = HRService()
    
    if st.button("刷新狀態 (Check Health)", key="hr_check_btn"):
        st.session_state['hr_check'] = True
        
    df = hr_service.check_agent_health()
    
    # Styling
    def highlight_status(val):
        color = ''
        if 'Zombie' in val:
            color = 'background-color: #ffcdd2' # Red
        elif 'Active' in val:
            color = 'background-color: #c8e6c9' # Green
        elif 'Missing' in val:
            color = 'background-color: #f5f5f5' # Grey
        elif 'Idle' in val:
            color = 'background-color: #fff9c4' # Yellow
        return color

    st.dataframe(df.style.applymap(highlight_status, subset=['Status']), use_container_width=True)
    
    st.markdown("### 處置建議")
    zombies = df[df['Status'].str.contains("Zombie")]
    if not zombies.empty:
        st.error(f"⚠️ 偵測到 {len(zombies)} 個 Zombie Agents! 建議檢查排程或手動觸發。")
        for _, z in zombies.iterrows():
            st.write(f"- **{z['Agent']}**: {z['Days Inactive']} 天無活動。")
    else:
        st.success("✅ 所有 Agent 運作正常")
    saas_card_end()
