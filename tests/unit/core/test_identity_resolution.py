import pytest
import uuid
import asyncio
from sqlalchemy import create_engine
from unittest.mock import patch
from src.data.database import init_db
from src.data.models import Base, User, UserIdentity
from src.repositories.user_repository import AlchemyUserRepository
from src.services.notification_service import NotificationService

@pytest.fixture
def test_repo():
    """Create an in-memory SQLite database for testing."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return AlchemyUserRepository(engine)

@patch('src.services.llm_onboarding_service.LLMOnboardingService.seed_defaults_for_user', return_value=None)
def test_identity_linking_and_resolution(mock_seed, test_repo):
    """Test creating a user and linking multiple identities."""
    async def run_test():
        # 1. Create User
        email = "test@example.com"
        user_uuid = test_repo.create_user(email, name="Tester")
        assert user_uuid is not None
        
        # 2. Resolve by email
        user = test_repo.get_by_identity("email", email)
        assert user is not None
        assert user['id'] == user_uuid
        
        # 3. Link LINE ID
        line_id = "U123456789"
        test_repo.link_identity(user_uuid, "line", line_id)
        
        # 4. Resolve by LINE ID
        user_by_line = test_repo.get_by_identity("line", line_id)
        assert user_by_line is not None
        assert user_by_line['id'] == user_uuid

    asyncio.run(run_test())

@patch('src.services.llm_onboarding_service.LLMOnboardingService.seed_defaults_for_user', return_value=None)
def test_notification_service_resolution(mock_seed, test_repo):
    """Test that NotificationService correctly resolves channel IDs via UUID."""
    async def run_test():
        # Setup user with multiple identities
        user_uuid = test_repo.create_user("notif@test.com")
        line_id = "LINE_USER_001"
        test_repo.link_identity(user_uuid, "line", line_id)
        
        # Notification service with injected repo
        service = NotificationService(adapters=[], user_repo=test_repo)
        
        # Resolve LINE ID from UUID
        resolved = await service._resolve_channel_id(user_uuid, "line")
        assert resolved == line_id
        
        # Resolve Email from UUID (fallback to primary email)
        resolved_email = await service._resolve_channel_id(user_uuid, "email")
        assert resolved_email == "notif@test.com"
        
        # Fallback for unknown provider (returns original UUID)
        fallback = await service._resolve_channel_id(user_uuid, "telegram")
        assert fallback == user_uuid

    asyncio.run(run_test())

@patch('src.services.llm_onboarding_service.LLMOnboardingService.seed_defaults_for_user', return_value=None)
def test_get_by_identity_email_fallback(mock_seed, test_repo):
    """Test get_by_identity falls back to users.email and links identity automatically."""
    async def run_test():
        # 1. Manually insert user into users table WITHOUT linking identity
        user_uuid = str(uuid.uuid4())
        email = "fallback_test@example.com"
        with test_repo.engine.begin() as conn:
            from sqlalchemy import text
            conn.execute(
                text("INSERT INTO users (id, email, name) VALUES (:id, :email, :name)"),
                {"id": user_uuid, "email": email, "name": "Fallback User"}
            )
            
        # 2. Query by identity (provider="email") - should trigger fallback and link identity
        user = test_repo.get_by_identity("email", email)
        assert user is not None
        assert user['id'] == user_uuid
        assert user['email'] == email
        
        # 3. Verify that identity was linked
        with test_repo.engine.connect() as conn:
            row = conn.execute(
                text("SELECT * FROM user_identities WHERE user_id = :uid"),
                {"uid": user_uuid}
            ).fetchone()
            assert row is not None
            assert row._mapping["provider"] == "email"
            assert row._mapping["identifier"] == email
            
        # 4. Resolve again - should succeed immediately via standard path
        user_again = test_repo.get_by_identity("email", email)
        assert user_again is not None
        assert user_again['id'] == user_uuid

    asyncio.run(run_test())
