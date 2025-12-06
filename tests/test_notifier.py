import pytest
from unittest.mock import MagicMock, patch
from src.notifier import EmailNotifier
import os

@patch('src.notifier.smtplib.SMTP')
def test_send_email_success(mock_smtp):
    # Setup values
    os.environ["SMTP_USER"] = "test@example.com"
    os.environ["SMTP_PASSWORD"] = "password"
    os.environ["EMAIL_RECIPIENT"] = "recipient@example.com"
    
    # Setup mock
    instance = mock_smtp.return_value
    instance.send_message.return_value = {}
    
    notifier = EmailNotifier()
    result = notifier.send_report("Subject", "Body")
    
    assert result is True
    instance.starttls.assert_called_once()
    instance.login.assert_called_with("test@example.com", "password")
    instance.send_message.assert_called()
    instance.quit.assert_called()

@patch('src.notifier.smtplib.SMTP')
def test_send_email_fail(mock_smtp):
    # Setup values
    os.environ["SMTP_USER"] = "test@example.com"
    os.environ["SMTP_PASSWORD"] = "password"
    
    # Setup mock to raise exception
    instance = mock_smtp.return_value
    instance.login.side_effect = Exception("Auth fail")
    
    notifier = EmailNotifier()
    result = notifier.send_report("Subject", "Body")
    
    assert result is False
    
def test_send_email_no_creds():
    if "SMTP_USER" in os.environ: del os.environ["SMTP_USER"]
    if "SMTP_PASSWORD" in os.environ: del os.environ["SMTP_PASSWORD"]
    
    notifier = EmailNotifier()
    result = notifier.send_report("Subject", "Body")
    
    assert result is False
