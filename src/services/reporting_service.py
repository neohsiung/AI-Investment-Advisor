from src.utils.logger import setup_logger
logger = setup_logger("ReportingService")

import markdown
from typing import Optional
from datetime import datetime

class ReportingService:
    """
    Service for converting Agent Markdown reports into Professional Institutional HTML formats.
    用於將 Agent Markdown 報告轉換為專業機構級 HTML 格式的服務。
    """
    
    def __init__(self):
        # markdown extensions for better formatting
        self.md = markdown.Markdown(extensions=[
            'tables', 
            'fenced_code', 
            'md_in_html',
            'sane_lists',
            'nl2br'
        ])
    
    def generate_professional_html(self, raw_markdown: str, title: str = "Strategic Investment Insight") -> str:
        """
        Converts raw markdown into a beautifully styled HTML string suitable for Emails or Web Views.
        將 Markdown 轉換為適合 Email 或網頁瀏覽的精美 HTML 字串。
        """
        try:
            html_body = self.md.convert(raw_markdown)
            
            # 1. Professional CSS Styles (Inline for email compatibility)
            css_styles = """
            <style>
                body {
                    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
                    line-height: 1.6;
                    color: #333333;
                    background-color: #f9fafc;
                    margin: 0;
                    padding: 0;
                }
                .container {
                    max-width: 800px;
                    margin: 20px auto;
                    background: #ffffff;
                    padding: 40px;
                    border-radius: 8px;
                    box-shadow: 0 4px 12px rgba(0,0,0,0.05);
                }
                .header {
                    border-bottom: 2px solid #1a365d;
                    padding-bottom: 20px;
                    margin-bottom: 30px;
                    text-align: center;
                }
                .header h1 {
                    color: #1a365d;
                    margin: 0 0 10px 0;
                    font-size: 28px;
                    font-weight: 700;
                    letter-spacing: -0.5px;
                }
                .header p {
                    color: #718096;
                    margin: 0;
                    font-size: 14px;
                    text-transform: uppercase;
                    letter-spacing: 1px;
                }
                h1, h2, h3, h4 {
                    color: #2d3748;
                    margin-top: 1.5em;
                    margin-bottom: 0.5em;
                    font-weight: 600;
                }
                h2 {
                    border-bottom: 1px solid #e2e8f0;
                    padding-bottom: 8px;
                    font-size: 22px;
                    color: #2b6cb0;
                }
                h3 {
                    font-size: 18px;
                }
                p {
                    margin-bottom: 1.2em;
                }
                ul, ol {
                    margin-bottom: 1.5em;
                    padding-left: 20px;
                }
                li {
                    margin-bottom: 0.5em;
                }
                table {
                    width: 100%;
                    border-collapse: collapse;
                    margin-bottom: 2em;
                    font-size: 14px;
                }
                th, td {
                    padding: 12px 15px;
                    text-align: left;
                    border-bottom: 1px solid #e2e8f0;
                }
                th {
                    background-color: #f7fafc;
                    color: #4a5568;
                    font-weight: 600;
                    text-transform: uppercase;
                    font-size: 12px;
                    letter-spacing: 0.5px;
                }
                tr:hover {
                    background-color: #fbfdff;
                }
                blockquote {
                    margin: 0 0 1.5em 0;
                    padding: 15px 20px;
                    background-color: #ebf8ff;
                    border-left: 4px solid #3182ce;
                    color: #2b6cb0;
                    font-style: italic;
                    border-radius: 0 4px 4px 0;
                }
                strong {
                    color: #1a202c;
                }
                .disclaimer {
                    margin-top: 40px;
                    padding-top: 20px;
                    border-top: 1px solid #edf2f7;
                    font-size: 11px;
                    color: #a0aec0;
                    text-align: justify;
                    line-height: 1.5;
                }
            </style>
            """
            
            # 2. Disclaimer / Footer
            disclaimer = """
            <div class="disclaimer">
                <strong>免責聲明 (Disclaimer):</strong> 本報告由 AI Investment Advisor 自動生成。報告內容僅供內部參考，不構成任何具體投資建議或財務指示。市場瞬息萬變，歷史數據（包含但不限於敘事復盤結果、模擬績效及報酬率分析）不代表未來實際績效表現。所有透過 Automated Trading 功能觸發之交易皆須經由授權人自行負責。本系統開發者與運營團隊不對依賴本報告做出之任何決策承擔任何直接或間接之損失責任。投資有賺有賠，執行前請詳閱各平台風險揭露說明文件並審慎評估自身風險承受能力。
            </div>
            """
            
            # 3. Final HTML Assembly
            date_str = datetime.now().strftime("%B %d, %Y")
            
            professional_html = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <meta charset="utf-8">
                <meta name="viewport" content="width=device-width, initial-scale=1.0">
                <title>{title}</title>
                {css_styles}
            </head>
            <body>
                <div class="container">
                    <div class="header">
                        <h1>{title}</h1>
                        <p>AI Investment Advisor • {date_str}</p>
                    </div>
                    
                    <div class="content">
                        {html_body}
                    </div>
                    
                    {disclaimer}
                </div>
            </body>
            </html>
            """
            
            return professional_html
            
        except Exception as e:
            logger.error(f"Failed to generate professional HTML report: {e}")
            return f"<h1>Error generating report</h1><p>{str(e)}</p><pre>{raw_markdown}</pre>"
