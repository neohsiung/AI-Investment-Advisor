import smtplib
from typing import Dict, Any
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
        """Return professional CSS styles for the email."""
        return """
        <style>
            body { font-family: 'Helvetica Neue', 'Segoe UI', Helvetica, Arial, sans-serif; line-height: 1.6; color: #333; background-color: #f4f4f4; padding: 20px; -webkit-font-smoothing: antialiased; }
            .container { max-width: 600px; margin: 0 auto; background: #ffffff; padding: 40px; border-radius: 12px; box-shadow: 0 4px 12px rgba(0,0,0,0.05); }
            h1 { color: #1a1a1a; font-size: 24px; font-weight: 700; border-bottom: 2px solid #007bff; padding-bottom: 15px; margin-top: 0; margin-bottom: 25px; letter-spacing: -0.5px; }
            h2 { color: #2c3e50; font-size: 20px; font-weight: 600; margin-top: 30px; margin-bottom: 15px; border-left: 4px solid #007bff; padding-left: 12px; }
            h3 { color: #555; font-size: 16px; font-weight: 600; margin-top: 25px; margin-bottom: 10px; text-transform: uppercase; letter-spacing: 0.5px; }
            p { margin-bottom: 18px; color: #4a4a4a; font-size: 16px; }
            strong { color: #222; font-weight: 600; }
            ul, ol { margin-bottom: 20px; padding-left: 20px; }
            li { margin-bottom: 8px; color: #4a4a4a; }
            a { color: #007bff; text-decoration: none; font-weight: 500; }
            a:hover { text-decoration: underline; }
            blockquote { border-left: 4px solid #e0e0e0; margin: 0 0 20px 0; padding: 10px 20px; color: #666; font-style: italic; background: #fafafa; border-radius: 0 4px 4px 0; }
            code { background-color: #f1f3f5; padding: 2px 5px; border-radius: 4px; font-family: 'SFMono-Regular', Consolas, 'Liberation Mono', Menlo, monospace; font-size: 0.9em; color: #e83e8c; }
            pre { background-color: #2b303b; color: #c0c5ce; padding: 15px; border-radius: 6px; overflow-x: auto; font-size: 14px; line-height: 1.45; }
            table { width: 100%; border-collapse: separate; border-spacing: 0; margin: 25px 0; border: 1px solid #e0e0e0; border-radius: 8px; overflow: hidden; }
            th, td { padding: 12px 15px; text-align: left; border-bottom: 1px solid #e0e0e0; }
            th { background-color: #f8f9fa; font-weight: 600; color: #333; text-transform: uppercase; font-size: 0.85em; letter-spacing: 0.5px; }
            tr:last-child td { border-bottom: none; }
            tr:hover { background-color: #f9f9f9; }
            .footer { margin-top: 40px; border-top: 1px solid #eee; padding-top: 25px; font-size: 13px; color: #999; text-align: center; }
            .alert { padding: 15px; margin-bottom: 25px; border-left: 4px solid transparent; border-radius: 4px; font-size: 15px; }
            .alert-info { color: #0c5460; background-color: #d1ecf1; border-color: #bee5eb; border-left-color: #17a2b8; }
            .alert-warning { color: #856404; background-color: #fff3cd; border-color: #ffeeba; border-left-color: #ffc107; }
            .alert-danger { color: #721c24; background-color: #f8d7da; border-color: #f5c6cb; border-left-color: #dc3545; }
            .badge { display: inline-block; padding: 0.25em 0.4em; font-size: 75%; font-weight: 700; line-height: 1; text-align: center; white-space: nowrap; vertical-align: baseline; border-radius: 0.25rem; }
            .badge-primary { color: #fff; background-color: #007bff; }
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

    def send_report(self, subject, content, to_email=None):
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

        # 1. Attach Plain Text Version (Backup)
        part1 = MIMEText(content, 'plain', 'utf-8')
        msg.attach(part1)

        # 2. Attach HTML Version (Beautified)
        # Convert Markdown to HTML
        try:
            html_body = markdown.markdown(content, extensions=['tables', 'fenced_code'])
            full_html = self._structure_html(subject, html_body)
            part2 = MIMEText(full_html, 'html', 'utf-8')
            msg.attach(part2)
        except Exception as e:
            self.logger.error(f"Markdown conversion failed: {e}. Sending plain text only.")
            # Already attached plain text, so just proceed

        try:
            self.logger.info(f"Connecting to SMTP server: {self.smtp_server}:{self.smtp_port}...")
            server = smtplib.SMTP(self.smtp_server, self.smtp_port)
            server.starttls()

            self.logger.info(f"Logging in as {self.sender_email}...")
            server.login(self.sender_email, self.sender_password)

            self.logger.info(f"Sending email to {recipient}...")
            server.send_message(msg)
            server.quit()

            self.logger.info("Email sent successfully.")
            return True
        except Exception as e:
            self.logger.error(f"Failed to send email: {e}", exc_info=True)
            return False

if __name__ == "__main__":
    # Test
    notifier = EmailNotifier()
    notifier.send_report("Test Report", "# Hello\nThis is a test.")
