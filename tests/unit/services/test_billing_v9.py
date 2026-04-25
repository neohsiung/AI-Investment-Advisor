import pytest
from unittest.mock import MagicMock, patch
from src.services.billing_service import BillingService, TierAccessDeniedError, QuotaExceededError

@pytest.fixture
def mock_db():
    with patch("src.services.billing_service.get_db_engine"), \
         patch("sqlalchemy.orm.sessionmaker") as mock_sessionmaker:
        mock_session = MagicMock()
        mock_sessionmaker.return_value.return_value = mock_session
        yield mock_session

def test_billing_init():
    service = BillingService("user-123")
    assert service._user_id == "user-123"

def test_get_user_subscription_free_default(mock_db):
    service = BillingService("user-123")
    
    # Mock user exists but has no subscription_id
    mock_user = MagicMock(id="user-123", subscription_id=None)
    mock_free_plan = MagicMock()
    mock_free_plan.name = "Free"
    mock_db.query.return_value.filter_by.return_value.first.side_effect = [
        mock_user,
        mock_free_plan
    ]
    
    plan = service.get_user_subscription()
    assert plan.name == "Free"

def test_check_quota_success(mock_db):
    service = BillingService("user-123")
    
    with patch.object(service, "get_user_subscription") as mock_get_sub:
        mock_plan = MagicMock(name="Pro", allowed_tiers=["fast", "smart"], monthly_usd_limit=100.0)
        mock_get_sub.return_value = mock_plan
        
        # Mock usage costs
        mock_user = MagicMock(current_billing_cycle_start=None)
        mock_db.query.return_value.filter_by.return_value.first.return_value = mock_user
        service._usage_repo.get_user_cycle_cost = MagicMock(return_value=50.0)
        
        assert service.check_quota("fast") is True

def test_check_quota_tier_denied(mock_db):
    service = BillingService("user-123")
    
    with patch.object(service, "get_user_subscription") as mock_get_sub:
        mock_plan = MagicMock(name="Free", allowed_tiers=["fast"], monthly_usd_limit=50.0)
        mock_get_sub.return_value = mock_plan
        
        mock_user = MagicMock()
        mock_db.query.return_value.filter_by.return_value.first.return_value = mock_user
        
        with pytest.raises(TierAccessDeniedError):
            service.check_quota("smart")

def test_check_quota_exceeded(mock_db):
    service = BillingService("user-123")
    
    with patch.object(service, "get_user_subscription") as mock_get_sub:
        mock_plan = MagicMock(name="Pro", allowed_tiers=["fast", "smart"], monthly_usd_limit=20.0)
        mock_get_sub.return_value = mock_plan
        
        mock_user = MagicMock(current_billing_cycle_start=None)
        mock_db.query.return_value.filter_by.return_value.first.return_value = mock_user
        service._usage_repo.get_user_cycle_cost = MagicMock(return_value=25.0)
        
        with pytest.raises(QuotaExceededError):
            service.check_quota("smart")
