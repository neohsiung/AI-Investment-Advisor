import streamlit as st
import pandas as pd
from src.utils.page_base import BasePage
from src.utils.components import saas_section_header, saas_card_start, saas_card_end, saas_alert


class AnalysisReportsPage(BasePage):
    """Investment advisory reports page"""
    
    def __init__(self):
        super().__init__("投資顧問報告 (Investment Advisory Reports)", "📊")
    
    def render(self):
        """Render reports content"""
        db_path = self.db_path
        
        from src.repositories.report_repository import AlchemyReportRepository  
        repo = AlchemyReportRepository(db_path)
        reports_df = repo.get_latest_reports(self.user['id'])

        if not reports_df.empty:
            from src.utils.time_utils import get_timezone
            user_tz = get_timezone()
            
            def convert_tz(x):
                try:
                    dt = pd.to_datetime(x)
                    if dt.tz is None:
                        dt = dt.tz_localize('UTC')
                    return dt.tz_convert(user_tz).strftime('%Y-%m-%d %H:%M:%S')
                except:
                    return x

            reports_df['display_date'] = reports_df['date'].apply(convert_tz)
            
            saas_section_header("歷史分析報告 (Archives)", "瀏覽歷史投資建議與分析報告")
            
            selected_display = st.selectbox("選擇報告日期 (Select Report Date)", reports_df['display_date'].unique())
            
            if selected_display:
                original_date = reports_df[reports_df['display_date'] == selected_display]['date'].values[0]
                report_content = reports_df[reports_df['date'] == original_date]['content'].values[0]
                
                saas_card_start(title=f"報告內容 - {selected_display}", icon="📄")
                st.markdown(report_content)
                saas_card_end()
        else:
            saas_alert("尚無報告可供檢視。報告將由排程系統自動生成。", style="info")


if __name__ == "__main__":
    AnalysisReportsPage().run()
