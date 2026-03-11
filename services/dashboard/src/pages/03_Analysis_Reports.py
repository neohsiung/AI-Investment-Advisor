import streamlit as st
import pandas as pd
from src.utils.page_base import BasePage
from src.utils.components import saas_section_header, saas_card_start, saas_card_end, saas_alert, saas_markdown


class AnalysisReportsPage(BasePage):
    """Investment advisory reports page"""
    
    def __init__(self):
        super().__init__("投資顧問報告 (Investment Advisory Reports)", ":material/lab_profile:")
    
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
                # Safe lookup directly by display_date
                date_rows = reports_df[reports_df['display_date'] == selected_display]
                if not date_rows.empty:
                    report_content = date_rows['content'].values[0]
                    
                    saas_card_start(title=f"報告內容 - {selected_display}", icon="📄")
                    if isinstance(report_content, str) and report_content.strip().startswith("<!DOCTYPE html>"):
                        import streamlit.components.v1 as components
                        # Professional HTML report: Render in components
                        # Adjust height dynamically - 800px is a good balance for full-page reports
                        components.html(report_content, height=800, scrolling=True)
                    else:
                        saas_markdown(report_content)
                    saas_card_end()
                else:
                    st.error("Selected date record not found.")
        else:
            saas_alert("尚無報告可供檢視。報告將由排程系統自動生成。", style="info")


if __name__ == "__main__":
    AnalysisReportsPage().run()
