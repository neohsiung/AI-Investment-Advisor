import asyncio
import sys
import os
import uuid
import logging
from decimal import Decimal
from datetime import datetime

# Ensure the project root is in sys.path
sys.path.append(os.getcwd())

from src.data.database import get_db_engine
from src.data.models import User, SubscriptionPlan, LLMUsageLog
from src.services.billing_service import BillingService, QuotaExceededError, TierAccessDeniedError
from src.utils.rate_limiter import rate_limit, RateLimitExceeded

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("Verify_16")

async def setup_test_data():
    from sqlalchemy.orm import sessionmaker
    Session = sessionmaker(bind=get_db_engine())
    session = Session()
    
    # 1. Create Free Plan
    free_plan = session.query(SubscriptionPlan).filter_by(name='Free').first()
    if not free_plan:
        free_plan = SubscriptionPlan(
            name='Free',
            monthly_usd_limit=Decimal('0.05'), # Very low limit for testing
            allowed_tiers=['nano', 'fast']
        )
        session.add(free_plan)
        session.commit()
    
    # 2. Create Test User
    test_user = session.query(User).filter_by(email='test_saas@example.com').first()
    if not test_user:
        test_user = User(
            id=str(uuid.uuid4()),
            email='test_saas@example.com',
            name='Test SaaS User',
            subscription_id=free_plan.id,
            current_billing_cycle_start=datetime.now()
        )
        session.add(test_user)
        session.commit()
    
    session.close()
    return test_user.id

async def test_quota_enforcement(user_id):
    logger.info("\n--- 🛡️ Testing Task 16.2 & 16.3: Quota Enforcement ---")
    billing = BillingService(user_id=user_id)
    
    # 1. Test Tier Access (Allowed)
    try:
        billing.check_quota(requested_tier='fast')
        logger.info("  ✅ Tier 'fast' access allowed for Free plan.")
    except Exception as e:
        logger.error(f"  ❌ Tier 'fast' should be allowed: {e}")

    # 2. Test Tier Access (Denied)
    try:
        billing.check_quota(requested_tier='advanced')
        logger.error("  ❌ Tier 'advanced' should be DENIED for Free plan.")
    except TierAccessDeniedError as e:
        logger.info(f"  ✅ Tier 'advanced' correctly denied: {e}")

    # 3. Simulate High Usage to hit Quota
    from sqlalchemy.orm import sessionmaker
    Session = sessionmaker(bind=get_db_engine())
    session = Session()
    
    # Add a log entry that exceeds the $0.05 limit
    log = LLMUsageLog(
        user_id=user_id,
        agent_name="TestAgent",
        total_cost_usd=Decimal('0.10'), # Exceeds $0.05
        created_at=datetime.now()
    )
    session.add(log)
    session.commit()
    session.close()
    
    # 4. Test Quota Limit (Exceeded)
    try:
        billing.check_quota(requested_tier='fast')
        logger.error("  ❌ Quota should be EXCEEDED.")
    except QuotaExceededError as e:
        logger.info(f"  ✅ Quota correctly exceeded: {e}")

async def test_rate_limiting():
    logger.info("\n--- 🛡️ Testing Task 16.4: Rate Limiting ---")
    
    @rate_limit(requests_per_minute=2)
    async def limited_function(user_id):
        return "OK"

    user_id = "user_rl_test"
    
    # Call 1 & 2 (OK)
    await limited_function(user_id=user_id)
    await limited_function(user_id=user_id)
    logger.info("  Calls 1 & 2 succeeded.")
    
    # Call 3 (Should fail)
    try:
        await limited_function(user_id=user_id)
        logger.error("  ❌ Call 3 should have been rate limited.")
    except RateLimitExceeded as e:
        logger.info(f"  ✅ Call 3 correctly rate limited: {e}")

async def main():
    user_id = await setup_test_data()
    await test_quota_enforcement(user_id)
    await test_rate_limiting()
    logger.info("\n✨ Phase 16 Verification Completed.")

if __name__ == "__main__":
    asyncio.run(main())
