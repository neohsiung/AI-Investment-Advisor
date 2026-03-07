from src.utils.logger import setup_logger
logger = setup_logger("ReportingService")

import markdown
import typing
from typing import List, Dict, Tuple, Any, Optional, Callable, Dict, List, Tuple, Any, Optional, Callable
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
                @import url('https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;600;700&display=swap');
                body {
                    font-family: 'Outfit', 'Segoe UI', Roboto, -apple-system, sans-serif;
                    line-height: 1.7;
                    color: #1e293b;
                    background-color: #f1f5f9;
                    margin: 0;
                    padding: 40px 20px;
                }
                .container {
                    max-width: 720px;
                    margin: 0 auto;
                    background: #ffffff;
                    padding: 50px;
                    border-radius: 20px;
                    box-shadow: 0 20px 25px -5px rgba(0, 0, 0, 0.1), 0 10px 10px -5px rgba(0, 0, 0, 0.04);
                    border: 1px solid #e2e8f0;
                }
                .header {
                    text-align: left;
                    margin-bottom: 40px;
                    border-left: 5px solid #0f172a;
                    padding-left: 20px;
                }
                .header h1 {
                    color: #0f172a;
                    margin: 0;
                    font-size: 32px;
                    font-weight: 700;
                    line-height: 1.2;
                }
                .header p {
                    color: #64748b;
                    margin: 8px 0 0 0;
                    font-size: 14px;
                    font-weight: 500;
                    text-transform: uppercase;
                    letter-spacing: 2px;
                }
                h1, h2, h3, h4 {
                    color: #0f172a;
                    margin-top: 2em;
                    margin-bottom: 0.8em;
                }
                h2 {
                    font-size: 24px;
                    font-weight: 600;
                    border-bottom: 2px solid #f1f5f9;
                    padding-bottom: 12px;
                    color: #2563eb;
                }
                h3 {
                    font-size: 18px;
                    font-weight: 600;
                    color: #334155;
                }
                p {
                    margin-bottom: 1.5em;
                }
                ul, ol {
                    margin-bottom: 1.5em;
                    padding-left: 25px;
                }
                li {
                    margin-bottom: 0.8em;
                }
                table {
                    width: 100%;
                    border-collapse: separate;
                    border-spacing: 0;
                    margin: 30px 0;
                    border: 1px solid #e2e8f0;
                    border-radius: 12px;
                    overflow: hidden;
                }
                th, td {
                    padding: 16px 20px;
                    text-align: left;
                    border-bottom: 1px solid #f1f5f9;
                }
                th {
                    background-color: #f8fafc;
                    color: #475569;
                    font-weight: 600;
                    font-size: 12px;
                    text-transform: uppercase;
                    letter-spacing: 0.05em;
                }
                tr:last-child td {
                    border-bottom: none;
                }
                blockquote {
                    margin: 40px 0;
                    padding: 24px 30px;
                    background-color: #f8fafc;
                    border-left: 6px solid #2563eb;
                    color: #1e293b;
                    font-style: italic;
                    font-size: 17px;
                    border-radius: 0 16px 16px 0;
                }
                strong {
                    color: #0f172a;
                    font-weight: 600;
                }
                .highlight {
                    background-color: #eff6ff;
                    color: #1e40af;
                    padding: 2px 6px;
                    border-radius: 4px;
                    font-weight: 600;
                }
                .disclaimer {
                    margin-top: 60px;
                    padding-top: 30px;
                    border-top: 1px solid #e2e8f0;
                    font-size: 12px;
                    color: #94a3b8;
                    text-align: justify;
                    line-height: 1.6;
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
