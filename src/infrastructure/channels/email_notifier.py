import smtplib
import typing
from typing import List, Dict, Tuple, Any, Optional, Callable, Dict, Any
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import os
import markdown
from dotenv import load_dotenv
from src.utils.logger import setup_logger

# Load environment variables from .env file
load_dotenv()

class EmailNotifier:
    def __init__(self, smtp_config: Dict[str, Any] = None):
        if smtp_config:
            self.smtp_server = smtp_config.get("server", "smtp.gmail.com")
            self.smtp_port = int(smtp_config.get("port", "587"))
            self.sender_email = smtp_config.get("user")
            self.sender_password = smtp_config.get("password")
            self.recipient_email = smtp_config.get("to_address")
        else:
            self.smtp_server = os.getenv("SMTP_HOST", "smtp.gmail.com")
            self.smtp_port = int(os.getenv("SMTP_PORT", "587"))
            self.sender_email = os.getenv("SMTP_USER")
            self.sender_password = os.getenv("SMTP_PASSWORD")
            self.recipient_email = os.getenv("EMAIL_RECIPIENT")
        self.logger = setup_logger("EmailNotifier")
        self.blocked_domains = ["example.com"]
        self.blocked_emails = ["your_email@gmail.com", "admin@example.com"]

    def _get_css(self):
        """Return modern responsive card CSS styles for the email."""
        return """
        <style>
            :root {
                color-scheme: light dark;
                supported-color-schemes: light dark;
            }
            body {
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
                line-height: 1.6;
                color: #1e293b;
                background-color: #f1f5f9;
                padding: 16px;
                margin: 0;
                -webkit-font-smoothing: antialiased;
            }
            .container {
                max-width: 680px;
                margin: 0 auto;
                background: #ffffff;
                padding: 32px;
                border-radius: 14px;
                box-shadow: 0 4px 20px rgba(0, 0, 0, 0.05);
                border: 1px solid #e2e8f0;
            }
            .header {
                padding-bottom: 16px;
                margin-bottom: 24px;
                border-bottom: 2px solid #3b82f6;
            }
            .header h1 {
                color: #0f172a;
                font-size: 22px;
                font-weight: 700;
                margin: 0;
                letter-spacing: -0.5px;
            }
            h1, h2 {
                color: #0f172a;
                font-size: 19px;
                font-weight: 700;
                margin-top: 28px;
                margin-bottom: 14px;
                letter-spacing: -0.3px;
            }
            h3 {
                color: #334155;
                font-size: 15px;
                font-weight: 600;
                margin-top: 22px;
                margin-bottom: 10px;
                letter-spacing: 0.2px;
            }
            p { margin-bottom: 16px; color: #334155; font-size: 15px; }
            strong { color: #0f172a; font-weight: 600; }
            ul, ol { margin-bottom: 18px; padding-left: 20px; }
            li { margin-bottom: 6px; color: #334155; font-size: 14.5px; }
            a { color: #2563eb; text-decoration: none; font-weight: 500; }
            a:hover { text-decoration: underline; }
            blockquote {
                border-left: 4px solid #3b82f6;
                margin: 16px 0;
                padding: 12px 18px;
                color: #334155;
                background: #f8fafc;
                border-radius: 0 8px 8px 0;
                font-size: 14.5px;
            }
            code {
                background-color: #f1f5f9;
                padding: 2px 6px;
                border-radius: 4px;
                font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
                font-size: 0.88em;
                color: #0369a1;
                font-weight: 600;
            }
            pre {
                background-color: #0f172a;
                color: #f8fafc;
                padding: 16px;
                border-radius: 8px;
                overflow-x: auto;
                font-size: 13.5px;
                line-height: 1.5;
            }
            table {
                width: 100%;
                border-collapse: collapse;
                margin: 20px 0;
                border: 1px solid #e2e8f0;
                border-radius: 8px;
                overflow: hidden;
                font-size: 13.5px;
            }
            th, td {
                padding: 10px 14px;
                text-align: left;
                border-bottom: 1px solid #e2e8f0;
            }
            th {
                background-color: #f8fafc;
                font-weight: 600;
                color: #475569;
                font-size: 0.82em;
                text-transform: uppercase;
                letter-spacing: 0.5px;
            }
            tr:last-child td { border-bottom: none; }
            tr:nth-child(even) td { background-color: #fcfdfe; }
            tr:hover td { background-color: #f1f5f9; }
            .footer {
                margin-top: 36px;
                border-top: 1px solid #e2e8f0;
                padding-top: 20px;
                font-size: 12.5px;
                color: #64748b;
                text-align: center;
            }
            .alert {
                padding: 14px 16px;
                margin-bottom: 20px;
                border-radius: 8px;
                font-size: 14.5px;
                border: 1px solid transparent;
            }
            .alert-info { color: #0369a1; background-color: #f0f9ff; border-color: #bae6fd; }
            .alert-warning { color: #b45309; background-color: #fffbeb; border-color: #fde68a; }
            .alert-danger { color: #b91c1c; background-color: #fef2f2; border-color: #fecaca; }
            .badge {
                display: inline-block;
                padding: 3px 8px;
                font-size: 75%;
                font-weight: 700;
                border-radius: 9999px;
            }
            .badge-primary { color: #ffffff; background-color: #2563eb; }

            /* Mobile Adaptation */
            @media only screen and (max-width: 600px) {
                body { padding: 8px; }
                .container { padding: 18px; border-radius: 10px; }
                h1 { font-size: 20px; }
                h2 { font-size: 17px; }
                p, li { font-size: 14px; }
                table { display: block; overflow-x: auto; -webkit-overflow-scrolling: touch; font-size: 12px; }
                th, td { padding: 8px 10px; }
            }

            /* Dark Mode Support */
            @media (prefers-color-scheme: dark) {
                body { background-color: #0b0f19; color: #cbd5e1; }
                .container { background: #131b2e; border-color: #1e293b; box-shadow: 0 4px 20px rgba(0, 0, 0, 0.4); }
                .header { border-bottom-color: #3b82f6; }
                .header h1 { color: #f8fafc; }
                h1, h2 { color: #f8fafc; }
                h3 { color: #94a3b8; }
                p, li { color: #cbd5e1; }
                strong { color: #f8fafc; }
                blockquote { background: #1e293b; color: #cbd5e1; border-left-color: #3b82f6; }
                code { background-color: #1e293b; color: #38bdf8; }
                table { border-color: #334155; }
                th { background-color: #1e293b; color: #94a3b8; border-bottom-color: #334155; }
                td { border-bottom-color: #1e293b; }
                tr:nth-child(even) td { background-color: #182238; }
                tr:hover td { background-color: #1e293b; }
                .footer { border-top-color: #1e293b; color: #64748b; }
            }
        </style>
        """

    def _structure_html(self, subject, html_content):
        """Wrap content in a proper HTML Email structure."""
        return f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>{subject}</title>
            {self._get_css()}
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>AI Investment Advisor</h1>
                </div>
                <div class="content">
                    {html_content}
                </div>
                <div class="footer">
                    <p>Generated by AI Investment Advisor Agent Swarm. Not financial advice.</p>
                </div>
            </div>
        </body>
        </html>
        """

    async def send_report(self, subject, content, to_email=None):
        """
        Send a beautified HTML report asynchronously using aiosmtplib.
        """
        import aiosmtplib
        if not self.sender_email or not self.sender_password:
            self.logger.warning("Email credentials not set. Skipping email notification.")
            return False

        recipient = to_email if to_email else self.recipient_email
        if not recipient:
             self.logger.warning("No recipient specified. Skipping email.")
             return False

        # Validate recipient
        if recipient in self.blocked_emails:
            self.logger.warning(f"Recipient {recipient} is in blocklist. Skipping email.")
            return False
            
        domain = recipient.split('@')[-1] if '@' in recipient else ''
        if domain in self.blocked_domains:
             self.logger.warning(f"Recipient domain {domain} is in blocklist. Skipping email.")
             return False

        msg = MIMEMultipart('alternative')
        msg['From'] = self.sender_email
        msg['To'] = recipient
        msg['Subject'] = subject

        # Attach Plain Text Version
        import re
        def strip_html(html):
            text = re.sub(r'<style.*?>.*?</style>', '', html, flags=re.DOTALL | re.IGNORECASE)
            text = re.sub(r'<[^>]+>', '', text)
            return text.strip()

        # Attach Parts
        try:
            if content.strip().lower().startswith("<!doctype html>") or "<html" in content[:200].lower():
                # Content is already fully formatted HTML
                plain_text = strip_html(content)
                part1 = MIMEText(plain_text, 'plain', 'utf-8')
                part2 = MIMEText(content, 'html', 'utf-8')
            else:
                # Content is Markdown
                part1 = MIMEText(content, 'plain', 'utf-8')
                html_body = markdown.markdown(content, extensions=['tables', 'fenced_code', 'nl2br'])
                full_html = self._structure_html(subject, html_body)
                part2 = MIMEText(full_html, 'html', 'utf-8')
            
            msg.attach(part1)
            msg.attach(part2)
        except Exception as e:
            self.logger.error(f"HTML attachment failed: {e}. Sending plain text only.")
            part1 = MIMEText(content, 'plain', 'utf-8')
            msg.attach(part1)

        try:
            self.logger.info(f"Connecting to SMTP server (async): {self.smtp_server}:{self.smtp_port}...")
            
            await aiosmtplib.send(
                msg,
                hostname=self.smtp_server,
                port=self.smtp_port,
                username=self.sender_email,
                password=self.sender_password,
                use_tls=self.smtp_port == 465,
                start_tls=self.smtp_port == 587,
                timeout=20
            )

            self.logger.info(f"Email sent successfully to {recipient}.")
            return True
        except Exception as e:
            self.logger.error(f"Failed to send async email: {e}")
            return False

if __name__ == "__main__":
    # Test
    notifier = EmailNotifier()
    notifier.send_report("Test Report", "# Hello\nThis is a test.")
