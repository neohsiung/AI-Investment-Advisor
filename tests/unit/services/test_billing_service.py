import pytest
from unittest.mock import MagicMock, patch
from src.services.billing_service import BillingService, QuotaExceededError, TierAccessDeniedError
from src.data.models import User, SubscriptionPlan

@pytest.fixture
def mock_db_session():
    return MagicMock()

def test_get_user_subscription_no_user(mock_db_session):
    with patch('src.services.billing_service.get_db_engine'):
        with patch('sqlalchemy.orm.sessionmaker') as mock_session_maker:
            mock_session = mock_session_maker.return_value.return_value
            mock_session.query.return_value.filter_by.return_value.first.return_value = None
            
            # Setup for default Free plan
            mock_free_plan = MagicMock(spec=SubscriptionPlan)
            mock_free_plan.name = "Free"
            mock_session.query.return_value.filter_by.return_value.first.side_effect = [None, mock_free_plan]
            
            service = BillingService(user_id="test_user")
            plan = service.get_user_subscription()
            
            assert plan.name == "Free"

def test_check_quota_tier_access_denied():
    user_id = "test_user"
    service = BillingService(user_id=user_id)
    
    with patch.object(service, 'get_user_subscription') as mock_get_sub:
        mock_plan = MagicMock(spec=SubscriptionPlan)
        mock_plan.name = "Basic"
        mock_plan.allowed_tiers = ["nano", "fast"]
        mock_get_sub.return_value = mock_plan
        
        with patch('src.services.billing_service.get_db_engine'):
            with patch('sqlalchemy.orm.sessionmaker') as mock_session_maker:
                # Mock user existence
                mock_session = mock_session_maker.return_value.return_value
                mock_session.query.return_value.filter_by.return_value.first.return_value = MagicMock(spec=User)
                
                with pytest.raises(TierAccessDeniedError):
                    service.check_quota(requested_tier="smart")

def test_check_quota_exceeded():
    user_id = "test_user"
    service = BillingService(user_id=user_id)
    
    with patch.object(service, 'get_user_subscription') as mock_get_sub:
        mock_plan = MagicMock(spec=SubscriptionPlan)
        mock_plan.name = "Pro"
        mock_plan.allowed_tiers = ["nano", "fast", "smart", "advanced"]
        mock_plan.monthly_usd_limit = 10.0
        mock_get_sub.return_value = mock_plan
        
        with patch('src.services.billing_service.get_db_engine'):
            with patch('sqlalchemy.orm.sessionmaker') as mock_session_maker:
                mock_session = mock_session_maker.return_value.return_value
                mock_user = MagicMock(spec=User)
                mock_user.current_billing_cycle_start = "2026-01-01"
                mock_session.query.return_value.filter_by.return_value.first.return_value = mock_user
                
                with patch.object(service._usage_repo, 'get_user_cycle_cost') as mock_get_cost:
                    mock_get_cost.return_value = 15.0 # Exceeds limit
                    
                    with pytest.raises(QuotaExceededError):
                        service.check_quota(requested_tier="smart")

def test_check_quota_success():
    user_id = "test_user"
    service = BillingService(user_id=user_id)
    
    with patch.object(service, 'get_user_subscription') as mock_get_sub:
        mock_plan = MagicMock(spec=SubscriptionPlan)
        mock_plan.name = "Pro"
        mock_plan.allowed_tiers = ["nano", "fast", "smart", "advanced"]
        mock_plan.monthly_usd_limit = 100.0
        mock_get_sub.return_value = mock_plan
        
        with patch('src.services.billing_service.get_db_engine'):
            with patch('sqlalchemy.orm.sessionmaker') as mock_session_maker:
                mock_session = mock_session_maker.return_value.return_value
                mock_user = MagicMock(spec=User)
                mock_user.current_billing_cycle_start = "2026-01-01"
                mock_session.query.return_value.filter_by.return_value.first.return_value = mock_user
                
                with patch.object(service._usage_repo, 'get_user_cycle_cost') as mock_get_cost:
                    mock_get_cost.return_value = 10.0 # Well under limit
                    
                    assert service.check_quota(requested_tier="smart") is True
