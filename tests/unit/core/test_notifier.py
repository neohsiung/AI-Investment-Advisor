import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from src.notifier import EmailNotifier
import os

@pytest.fixture
def anyio_backend():
    return 'asyncio'

@pytest.mark.anyio
@patch('aiosmtplib.send', AsyncMock(return_value=True))
async def test_send_email_success():
    # Setup values
    os.environ["SMTP_USER"] = "sender@test.com"
    os.environ["SMTP_PASSWORD"] = "password" # pragma: allowlist secret
    os.environ["EMAIL_RECIPIENT"] = "recipient@test.com"

    notifier = EmailNotifier()
    result = await notifier.send_report("Subject", "Body")

    assert result is True

@pytest.mark.anyio
@patch('aiosmtplib.send')
async def test_send_email_fail(mock_send):
    # Setup values
    os.environ["SMTP_USER"] = "test@example.com"
    os.environ["SMTP_PASSWORD"] = "password" # pragma: allowlist secret

    # Setup mock to raise exception
    mock_send.side_effect = Exception("Auth fail")

    notifier = EmailNotifier()
    result = await notifier.send_report("Subject", "Body")

    assert result is False

@pytest.mark.anyio
async def test_send_email_no_creds():
    if "SMTP_USER" in os.environ: del os.environ["SMTP_USER"]
    if "SMTP_PASSWORD" in os.environ: del os.environ["SMTP_PASSWORD"]

    notifier = EmailNotifier()
    result = await notifier.send_report("Subject", "Body")

    assert result is False
