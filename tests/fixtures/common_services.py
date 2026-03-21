import pytest
from unittest.mock import AsyncMock, MagicMock

@pytest.fixture
def mock_db_session():
    """Shared fixture for database session."""
    session = MagicMock()
    session.execute = AsyncMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    session.close = AsyncMock()
    return session

@pytest.fixture
def mock_llm_gateway():
    """Shared fixture for LLMGateway."""
    gateway = MagicMock()
    gateway.generate_response = AsyncMock(return_value={"content": "mocked response", "status": "success"})
    return gateway

@pytest.fixture
def mock_interaction_service():
    """Shared fixture for InteractionService."""
    service = MagicMock()
    service.send_message = AsyncMock()
    return service

@pytest.fixture
def mock_notification_service():
    """Shared fixture for NotificationService."""
    service = MagicMock()
    service.notify = AsyncMock()
    return service
