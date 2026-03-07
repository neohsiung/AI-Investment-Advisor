import pytest
import datetime
import logging
from typing import Any, Dict, List, Tuple, Optional, Callable
from unittest.mock import MagicMock, patch

from src.services.verification_service import VerificationService
from src.repositories.verification_repository import AlchemyVerificationRepository
from src.services.notification_service import NotificationService

@pytest.fixture
def anyio_backend():
    return 'asyncio'

@pytest.fixture
def mock_repo():
    return MagicMock(spec=AlchemyVerificationRepository)

@pytest.fixture
def mock_notification():
    return MagicMock(spec=NotificationService)

@pytest.fixture
def service(mock_repo, mock_notification):
    return VerificationService(repo=mock_repo, notification_service=mock_notification)

@pytest.mark.anyio
async def test_connectivity_success(service, mock_notification):
    # Mock notify_all returning success for LINE
    mock_notification.notify_all.return_value = {"LineBotAdapter": (True, "OK")}
    
    success, msg = await service.test_connectivity("user123", "line")
    
    assert success is True
    assert msg == "OK"
    mock_notification.notify_all.assert_called_once()
    args, kwargs = mock_notification.notify_all.call_args
    assert kwargs['capture_error'] is True

@pytest.mark.anyio
async def test_connectivity_failure(service, mock_notification):
    # Mock notify_all returning failure
    mock_notification.notify_all.return_value = {"LineBotAdapter": (False, "Invalid Token")}
    
    success, msg = await service.test_connectivity("user123", "line")
    
    assert success is False
    assert "Invalid Token" in msg

@pytest.mark.anyio
async def test_connectivity_adapter_not_found(service, mock_notification):
     mock_notification.notify_all.return_value = {"EmailAdapter": (True, "OK")}
     
     success, msg = await service.test_connectivity("user123", "line")
     assert success is False
     assert "not found" in msg

@pytest.mark.anyio
async def test_initiate_verification_flow(service, mock_repo, mock_notification):
    mock_notification.notify_all.return_value = {"LineBotAdapter": (True, "OK")}
    
    success, msg, vid = await service.initiate_verification("user_1", "line", timeout_hours=2)
    
    assert success is True
    assert vid is not None # Simply ensure a verification ID is returned
    mock_repo.create_verification.assert_called_once()

@pytest.mark.anyio
async def test_verify_reply_success(service, mock_repo, mock_notification):
    # Mock pending verification
    mock_repo.get_pending_verification.return_value = {
        "id": "v1", "user_id": "u1", "channel": "line", "code": "OK"
    }
    
    # Act
    result = await service.verify_reply("u1", "ok", "line") # Case insensitive match
    
    assert result is True
    mock_repo.update_status.assert_called_with("v1", "verified")
    mock_notification.notify_all.assert_called() # Confirmation sent

@pytest.mark.anyio
async def test_verify_reply_fail(service, mock_repo):
    mock_repo.get_pending_verification.return_value = {
        "id": "v1", "user_id": "u1", "channel": "line", "code": "OK"
    }
    
    result = await service.verify_reply("u1", "WRONG_CODE", "line")
    
    assert result is False
    mock_repo.update_status.assert_not_called()

@pytest.mark.anyio
async def test_verify_any_reply_success(service, mock_repo, mock_notification):
    mock_repo.get_any_pending_verification.return_value = {
        "id": "v1", "user_id": "u1", "channel": "line", "code": "OK"
    }
    
    result = await service.verify_any_reply("u1", "OK")
    
    assert result is True
    mock_repo.update_status.assert_called_with("v1", "verified")
