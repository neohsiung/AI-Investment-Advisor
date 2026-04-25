"""
Extended tests for NotificationService.
測試通知服務的進階功能。
"""
import pytest
import os
from unittest.mock import MagicMock, patch, AsyncMock
from src.services.notification_service import NotificationService

@pytest.fixture
def anyio_backend():
    return 'asyncio'

@pytest.mark.anyio
async def test_notify_all_with_custom_adapters():
    """Test notify_all with custom adapter injection."""
    mock_line = MagicMock()
    mock_email = MagicMock()
    mock_web = MagicMock()
    
    mock_line.send_alert = AsyncMock(return_value=True)
    mock_email.send_alert = AsyncMock(return_value=True)
    mock_web.send_alert = AsyncMock(return_value=True)
    
    # We need to set the name on the mock itself or its class
    type(mock_line).msg = "LineBotAdapter" # Placeholder to make it accessible
    mock_line.__class__.__name__ = "LineBotAdapter"
    mock_email.__class__.__name__ = "EmailAdapter"
    mock_web.__class__.__name__ = "WebAdapter"
    
    service = NotificationService(adapters=[mock_line, mock_email, mock_web])
    
    results = await service.notify_all(
        title="Test Alert",
        content="Test content",
        user_id="test_user"
    )
    
    assert len(results) == 3
    mock_line.send_alert.assert_called_once()
    mock_email.send_alert.assert_called_once()
    mock_web.send_alert.assert_called_once()

@pytest.mark.anyio
async def test_notify_all_handles_adapter_failures():
    """Test notify_all continues when individual adapters fail."""
    mock_line = MagicMock()
    mock_email = MagicMock()
    mock_web = MagicMock()
    
    # Make email fail
    mock_email.send_alert = AsyncMock(side_effect=Exception("Email error"))
    mock_line.send_alert = AsyncMock(return_value=True)
    mock_web.send_alert = AsyncMock(return_value=True)

    mock_line.__class__.__name__ = "LineBotAdapter"
    mock_email.__class__.__name__ = "EmailAdapter"
    mock_web.__class__.__name__ = "WebAdapter"
    
    service = NotificationService(adapters=[mock_line, mock_email, mock_web])
    
    results = await service.notify_all(
        title="Test Alert",
        content="Test content"
    )
    
    # Should have results for all adapters
    assert len(results) == 3
    # LINE and Web should succeed
    mock_line.send_alert.assert_called_once()
    mock_web.send_alert.assert_called_once()

@pytest.mark.anyio
async def test_send_report_filters_channels():
    """Test send_report only uses email and web channels."""
    mock_line = MagicMock()
    mock_email = MagicMock()
    mock_web = MagicMock()
    
    mock_line.send_alert = AsyncMock(return_value=True)
    mock_email.send_alert = AsyncMock(return_value=True)
    mock_web.send_alert = AsyncMock(return_value=True)
    
    mock_line.__class__.__name__ = "LineBotAdapter"
    mock_email.__class__.__name__ = "EmailAdapter"
    mock_web.__class__.__name__ = "WebAdapter"
    
    service = NotificationService(adapters=[mock_line, mock_email, mock_web])
    
    await service.send_report(
        subject="Test Report",
        content="Report content",
        user_id="test_user"
    )
    
    # LINE should not be called for reports
    assert not mock_line.send_alert.called
    # Email and Web should be called
    mock_email.send_alert.assert_called_once()
    mock_web.send_alert.assert_called_once()

@pytest.mark.anyio
async def test_notify_all_with_actions():
    """Test notify_all passes actions to adapters."""
    mock_adapter = MagicMock()
    mock_adapter.send_alert = AsyncMock(return_value=True)
    mock_adapter.__class__.__name__ = "GenericAdapter"
    
    service = NotificationService(adapters=[mock_adapter])
    
    actions = [{"label": "View", "url": "/reports/123"}]
    
    await service.notify_all(
        title="Alert",
        content="Content",
        actions=actions
    )
    
    call_args = mock_adapter.send_alert.call_args
    assert call_args[1]["actions"] == actions

@pytest.mark.anyio
async def test_notify_all_with_extra_kwargs():
    """Test notify_all passes extra kwargs to adapters."""
    mock_adapter = MagicMock()
    mock_adapter.send_alert = AsyncMock(return_value=True)
    mock_adapter.__class__.__name__ = "GenericAdapter"
    
    service = NotificationService(adapters=[mock_adapter])
    
    await service.notify_all(
        title="Alert",
        content="Content",
        level="ERROR",
        source="TestSource"
    )
    
    call_args = mock_adapter.send_alert.call_args
    assert call_args[1]["level"] == "ERROR"
    assert call_args[1]["source"] == "TestSource"

@pytest.mark.anyio
async def test_notify_all_returns_results():
    """Test notify_all returns success status for each adapter."""
    mock_adapter1 = MagicMock()
    mock_adapter2 = MagicMock()
    
    mock_adapter1.__class__.__name__ = "Adapter1"
    mock_adapter2.__class__.__name__ = "Adapter2"
    
    mock_adapter1.send_alert = AsyncMock(return_value=True)
    mock_adapter2.send_alert = AsyncMock(return_value=False)
    
    service = NotificationService(adapters=[mock_adapter1, mock_adapter2])
    
    results = await service.notify_all(title="Test", content="Content")
    
    assert results["Adapter1"] is True
    assert results["Adapter2"] is False

@pytest.mark.anyio
async def test_send_report_with_source():
    """Test send_report passes source parameter."""
    mock_adapter = MagicMock()
    mock_adapter.__class__.__name__ = "EmailAdapter"
    mock_adapter.send_alert = AsyncMock(return_value=True)
    
    service = NotificationService(adapters=[mock_adapter])
    
    await service.send_report(
        subject="Daily Report",
        content="Content",
        source="DailyWorkflow"
    )
    
    call_args = mock_adapter.send_alert.call_args
    assert call_args[1]["source"] == "DailyWorkflow"

@pytest.mark.anyio
async def test_notify_all_with_channel_filter():
    """Test notify_all respects channel filter."""
    mock_line = MagicMock()
    mock_email = MagicMock()
    
    mock_line.__class__.__name__ = "LineBotAdapter"
    mock_line.send_alert = AsyncMock(return_value=True)
    mock_email.__class__.__name__ = "EmailAdapter"
    mock_email.send_alert = AsyncMock(return_value=True)
    
    service = NotificationService(adapters=[mock_line, mock_email])
    
    await service.notify_all(
        title="Test",
        content="Content",
        channels=["email"]
    )
    
    # Only email should be called
    assert not mock_line.send_alert.called
    mock_email.send_alert.assert_called_once()


def test_notification_filters_import_from_domain():
    """Verify that INotificationFilter is correctly imported from domain.interfaces."""
    import inspect
    from src.services.notification_filters import InterestBasedFilter
    from src.domain.interfaces import INotificationFilter
    
    # Check that InterestBasedFilter is indeed a subclass of INotificationFilter from domain.interfaces
    assert issubclass(InterestBasedFilter, INotificationFilter)

@pytest.mark.anyio
async def test_distribute_report_includes_web_channel():
    """Verify distribute_report sends to both email AND web channels."""
    from src.services.workflow_service import DailyWorkflow
    from unittest.mock import patch, ANY
    
    workflow = DailyWorkflow(user_id="test_user")
    
    with patch("src.services.notification_settings_manager.NotificationSettingsManager.get_active_notification_channels") as mock_channels, \
         patch("src.services.notification_service.NotificationService.notify_all", new_callable=AsyncMock) as mock_notify:
        
        mock_channels.return_value = ["web", "email"]
        await workflow.distribute_report(content="Test HTML Content")
        
        # Verify that notify_all was called with the correct channels
        mock_notify.assert_called_once()
        call_kwargs = mock_notify.call_args[1]
        
        assert "email" in call_kwargs.get('channels', [])
        assert "web" in call_kwargs.get('channels', [])
        assert call_kwargs.get('category') == "report"
