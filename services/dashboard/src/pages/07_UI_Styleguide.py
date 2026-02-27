"""
UI Styleguide / Storybook Page
展示與規範應用程式的 UI 組件。
"""
import streamlit as st
from src.utils.page_base import BasePage
from src.utils.components import (
    saas_card_start, saas_card_end, saas_metric, 
    saas_badge, saas_alert, saas_section_header
)

class UIStyleguidePage(BasePage):
    def __init__(self):
        super().__init__("UI Styleguide", ":material/palette:")
        
    def render(self):
        st.markdown("""
        本頁面作為系統的 **UI Storybook**，定義了 2026 專業 SaaS 風格的組件規範。
        開發新功能時，請優先使用 `src.utils.components` 中的組件以維持視覺一致性。
        """)
        
        # 1. Typography & Colors
        saas_section_header("Design Tokens", "核心設計變量與色彩規範")
        
        c1, c2, c3, c4 = st.columns(4)
        with c1:
            st.markdown('<div style="background:var(--saas-primary); height:60px; border-radius:8px; display:flex; align-items:center; justify-content:center; color:white; font-weight:bold;">Primary</div>', unsafe_allow_html=True)
            st.caption("--saas-primary")
        with c2:
            st.markdown('<div style="background:var(--saas-primary-gradient); height:60px; border-radius:8px; display:flex; align-items:center; justify-content:center; color:white; font-weight:bold;">Gradient</div>', unsafe_allow_html=True)
            st.caption("--saas-primary-gradient")
        with c3:
            st.markdown('<div style="background:var(--saas-success); height:60px; border-radius:8px; display:flex; align-items:center; justify-content:center; color:white; font-weight:bold;">Success</div>', unsafe_allow_html=True)
            st.caption("--saas-success")
        with c4:
            st.markdown('<div style="background:var(--saas-danger); height:60px; border-radius:8px; display:flex; align-items:center; justify-content:center; color:white; font-weight:bold;">Danger</div>', unsafe_allow_html=True)
            st.caption("--saas-danger")
            
        # 2. Key Metrics
        saas_section_header("Key Metrics", "現代化的指標卡片，支援趨勢顯示與圖示")
        
        m1, m2, m3, m4 = st.columns(4)
        with m1:
            saas_metric("Total Assets", "$12,450.00", "+5.2%", icon="💰")
        with m2:
            saas_metric("Net Profit", "$3,210.00", "+12.4%", icon="📈")
        with m3:
            saas_metric("Leverage", "1.25x", "-0.1x", delta_color="inverse", icon="⚖️")
        with m4:
            saas_metric("Active Tickers", "18", icon="🎯")
            
        # 3. Cards & Containers
        saas_section_header("Content Containers", "卡片式容器，用於封裝資訊塊")
        
        saas_card_start("Market Performance", "Real-time overview of major indices", icon="📉")
        st.write("這是卡片內部的內容。卡片具備細微的陰影、圓角與 Hover 提升效果。")
        st.info("💡 提示：可以在卡片內放置圖表或數據框。")
        saas_card_end()
        
        # 4. Badges & Labels
        saas_section_header("Status Badges", "各種狀態標籤 (Pills)")
        
        cols = st.columns(5)
        badges = [
            ("BUY", "success"), ("HOLD", "warning"), ("SELL", "danger"), 
            ("PENDING", "info"), ("CLOSED", "neutral")
        ]
        for i, (text, style) in enumerate(badges):
            with cols[i]:
                st.markdown(saas_badge(text, style), unsafe_allow_html=True)
                st.caption(f"Style: {style}")
                
        # 5. Alerts & Notifications
        saas_section_header("Alert Banners", "簡潔且層次分明的警告與提示橫幅")
        
        saas_alert("您的資產組合今日表現優於市場 2.5%！", style="success", title="表現優異")
        saas_alert("檢測到高槓桿風險，請儘速檢查持倉。", style="warning", title="風險提示")
        saas_alert("OpenRouter API 連線中斷，請檢查網路設定。", style="danger", title="系統錯誤")
        saas_alert("系統將於本日 22:00 進行維護。", style="info")

if __name__ == "__main__":
    UIStyleguidePage().run()
