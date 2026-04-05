import uuid
import logging
from decimal import Decimal
from datetime import datetime
from src.data.database import get_db_engine
from src.data.models import User, SubscriptionPlan

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("SeedSaaS")

def seed_enterprise_subscription():
    """
    Ensures that a high-tier subscription exists and the default user is on it.
    """
    from sqlalchemy.orm import sessionmaker
    Session = sessionmaker(bind=get_db_engine())
    session = Session()
    
    try:
        # 1. Ensure 'Unlimited' Plan exists
        unlimited_plan = session.query(SubscriptionPlan).filter_by(name='Unlimited').first()
        if not unlimited_plan:
            logger.info("Creating 'Unlimited' subscription plan...")
            unlimited_plan = SubscriptionPlan(
                id=str(uuid.uuid4()),
                name='Unlimited',
                monthly_usd_limit=Decimal('999999.99'), # Practically unlimited
                allowed_tiers=["nano", "fast", "smart", "advanced"],
                max_parallel_agents=50,
                features={"proactive_alerts": True, "meta_cognition": True}
            )
            session.add(unlimited_plan)
            session.commit()
        else:
            # Update to ensure full access
            unlimited_plan.monthly_usd_limit = Decimal('999999.99')
            unlimited_plan.allowed_tiers = ["nano", "fast", "smart", "advanced"]
            session.commit()

        # 2. Update 'system' user (Used in local dev)
        system_user = session.query(User).filter_by(id='system').first()
        if not system_user:
            # Maybe check by email? Or just create it
            system_user = session.query(User).filter_by(email='system@advisor.ai').first()
            
        if system_user:
            logger.info(f"Subscribing user '{system_user.id}' to Unlimited plan...")
            system_user.subscription_id = unlimited_plan.id
            system_user.current_billing_cycle_start = datetime.now()
            session.commit()
            logger.info("✅ System user is now on Unlimited plan.")
        else:
            # Create a default system user if missing
            logger.info("Creating default 'system' user on Unlimited plan...")
            new_user = User(
                id='system',
                email='system@advisor.ai',
                name='System Developer',
                subscription_id=unlimited_plan.id,
                current_billing_cycle_start=datetime.now()
            )
            session.add(new_user)
            session.commit()

    except Exception as e:
        session.rollback()
        logger.error(f"Seeding failed: {e}")
    finally:
        session.close()

if __name__ == "__main__":
    seed_enterprise_subscription()
