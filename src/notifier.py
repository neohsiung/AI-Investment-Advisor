import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import os
from dotenv import load_dotenv
from src.utils.logger import setup_logger

# Load environment variables from .env file
load_dotenv()

class EmailNotifier:
    def __init__(self):
        self.smtp_server = os.getenv("SMTP_HOST", "smtp.gmail.com")
        self.smtp_port = int(os.getenv("SMTP_PORT", "587"))
        self.sender_email = os.getenv("SMTP_USER")
        self.sender_password = os.getenv("SMTP_PASSWORD")
        self.recipient_email = os.getenv("EMAIL_RECIPIENT")
        self.logger = setup_logger("EmailNotifier")

    def send_report(self, subject, content):
        if not self.sender_email or not self.sender_password:
            self.logger.warning("Email credentials not set. Skipping email notification.")
            return False

        msg = MIMEMultipart()
        msg['From'] = self.sender_email
        msg['To'] = self.recipient_email
        msg['Subject'] = subject

        msg.attach(MIMEText(content, 'plain', 'utf-8')) # Use plain text for markdown readability

        try:
            self.logger.info(f"Connecting to SMTP server: {self.smtp_server}:{self.smtp_port}...")
            server = smtplib.SMTP(self.smtp_server, self.smtp_port)
            server.starttls()
            
            self.logger.info(f"Logging in as {self.sender_email}...")
            server.login(self.sender_email, self.sender_password)
            
            self.logger.info(f"Sending email to {self.recipient_email}...")
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
