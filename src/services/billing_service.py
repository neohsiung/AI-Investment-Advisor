"""
Billing & Quota Service — SaaS Layer [Phase 16].
計費與配額服務 — 負責檢查用戶訂閱狀態、可用額度與模型存取權。
"""

import logging
from typing import Optional, List, Dict, Any
from src.data.database import get_db_engine
from src.repositories.usage_repository import UsageRepository
from src.data.models import User, SubscriptionPlan

logger = logging.getLogger(__name__)

class QuotaExceededError(Exception):
    """Raised when user exceeds their monthly USD limit."""
    pass

class TierAccessDeniedError(Exception):
    """Raised when user tries to access a model tier not included in their plan."""
    pass

class BillingService:
    """
    Manages user subscriptions and enforces API quotas.
    """
    def __init__(self, user_id: str, db_session=None):
        self._user_id = user_id
        self._db = db_session # If provided, use it. Otherwise, we fetch on demand.
        self._usage_repo = UsageRepository()

    def get_user_subscription(self) -> Optional[SubscriptionPlan]:
        """
        Fetch the current subscription plan for the user.
        """
        from sqlalchemy.orm import sessionmaker
        Session = sessionmaker(bind=get_db_engine())
        session = Session()
        try:
            user = session.query(User).filter_by(id=self._user_id).first()
            if not user or not user.subscription_id:
                # Default to Free plan if none set
                free_plan = session.query(SubscriptionPlan).filter_by(name='Free').first()
                return free_plan
            
            plan = session.query(SubscriptionPlan).filter_by(id=user.subscription_id).first()
            return plan
        except Exception as e:
            logger.error(f"Failed to fetch user subscription: {e}")
            return None
        finally:
            session.close()

    def check_quota(self, requested_tier: str) -> bool:
        """
        Verifies if the user is allowed to make this request.
        1. Check model tier access.
        2. Check monthly USD limit.
        """
        from sqlalchemy.orm import sessionmaker
        Session = sessionmaker(bind=get_db_engine())
        session = Session()
        try:
            user = session.query(User).filter_by(id=self._user_id).first()
            if not user:
                return True # Allow system/unknown for now or throw error
            
            # 1. Fetch Subscription Plan
            plan = self.get_user_subscription()
            if not plan:
                logger.warning(f"No subscription plan found for user {self._user_id}. Blocking.")
                raise TierAccessDeniedError("No subscription plan active.")

            # 2. Check Tier Access
            allowed_tiers = plan.allowed_tiers or ["nano", "fast"]
            if requested_tier not in allowed_tiers:
                logger.warning(f"User {self._user_id} plan ({plan.name}) does not allow tier {requested_tier}.")
                raise TierAccessDeniedError(f"Upgrade to access '{requested_tier}' tier models.")

            # 3. Check Monthly USD Limit
            # We fetch cost since cycle start
            since = user.current_billing_cycle_start
            current_spend = self._usage_repo.get_user_cycle_cost(self._user_id, since)
            
            limit = float(plan.monthly_usd_limit or 0.0)
            if limit > 0 and current_spend >= limit:
                logger.error(f"User {self._user_id} exceeded quota: ${current_spend:.2f} / ${limit:.2f}")
                raise QuotaExceededError(f"Monthly quota reached (${current_spend:.2f}). Please upgrade.")

            return True
            
        except (TierAccessDeniedError, QuotaExceededError):
            raise
        except Exception as e:
            logger.error(f"BillingService Error: {e}", exc_info=True)
            return True # Fallback to allow if unexpected error to avoid blocking active users
        finally:
            session.close()
