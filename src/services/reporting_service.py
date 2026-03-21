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
            
            html_body = html_body.replace('<h2>', '<h2 style="font-size: 20px; font-weight: 600; border-bottom: 2px solid #e2e8f0; padding-bottom: 8px; color: #2563eb; margin-top: 24px; margin-bottom: 12px; font-family: sans-serif;">')
            html_body = html_body.replace('<h3>', '<h3 style="font-size: 16px; font-weight: 600; color: #334155; margin-top: 20px; margin-bottom: 10px; font-family: sans-serif;">')
            html_body = html_body.replace('<p>', '<p style="margin-bottom: 16px; font-family: sans-serif; font-size: 14px; line-height: 1.6; color: #1e293b;">')
            html_body = html_body.replace('<ul>', '<ul style="margin-bottom: 16px; padding-left: 20px; font-family: sans-serif; font-size: 14px; line-height: 1.6; color: #1e293b;">')
            html_body = html_body.replace('<ol>', '<ol style="margin-bottom: 16px; padding-left: 20px; font-family: sans-serif; font-size: 14px; line-height: 1.6; color: #1e293b;">')
            html_body = html_body.replace('<li>', '<li style="margin-bottom: 8px;">')
            html_body = html_body.replace('<table>', '<table style="width: 100%; border-collapse: collapse; margin: 24px 0; border: 1px solid #e2e8f0; font-family: sans-serif; font-size: 13px;">')
            html_body = html_body.replace('<th>', '<th style="padding: 12px; text-align: left; background-color: #f8fafc; color: #475569; font-weight: 600; border-bottom: 2px solid #e2e8f0;">')
            html_body = html_body.replace('<td>', '<td style="padding: 12px; text-align: left; border-bottom: 1px solid #f1f5f9; color: #1e293b;">')
            html_body = html_body.replace('<blockquote>', '<blockquote style="margin: 24px 0; padding: 16px 20px; background-color: #f8fafc; border-left: 4px solid #2563eb; color: #1e293b; font-style: italic; border-radius: 0 8px 8px 0; font-family: sans-serif;">')
            
            # 2. Disclaimer / Footer (with inline styles)
            disclaimer = """
            <div style="margin-top: 40px; padding-top: 20px; border-top: 1px solid #e2e8f0; font-size: 12px; color: #94a3b8; text-align: justify; line-height: 1.6; font-family: sans-serif;">
                <strong style="color: #64748b;">免責聲明 (Disclaimer):</strong> 本報告由 AI Investment Advisor 自動生成。報告內容僅供內部參考，不構成任何具體投資建議或財務指示。市場瞬息萬變，歷史數據（包含但不限於敘事復盤結果、模擬績效及報酬率分析）不代表未來實際績效表現。所有透過 Automated Trading 功能觸發之交易皆須經由授權人自行負責。本系統開發者與運營團隊不對依賴本報告做出之任何決策承擔任何直接或間接之損失責任。投資有賺有賠，執行前請詳閱各平台風險揭露說明文件並審慎評估自身風險承受能力。
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
            </head>
            <body style="font-family: Arial, Helvetica, sans-serif; line-height: 1.6; color: #1e293b; background-color: #f1f5f9; margin: 0; padding: 20px;">
                <div style="max-width: 680px; margin: 0 auto; background: #ffffff; padding: 30px; border-radius: 12px; border: 1px solid #e2e8f0;">
                    <div style="text-align: left; margin-bottom: 30px; border-left: 4px solid #0f172a; padding-left: 16px;">
                        <h1 style="color: #0f172a; margin: 0; font-size: 24px; font-weight: 700; font-family: sans-serif;">{title}</h1>
                        <p style="color: #64748b; margin: 6px 0 0 0; font-size: 13px; font-weight: 500; text-transform: uppercase; letter-spacing: 1px; font-family: sans-serif;">AI Investment Advisor • {date_str}</p>
                    </div>
                    
                    <div style="font-family: sans-serif; font-size: 14px; color: #1e293b;">
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
