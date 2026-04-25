import sys
import os
from decimal import Decimal
from datetime import datetime
from sqlalchemy import text
from sqlalchemy.orm import sessionmaker

# Add src to path
sys.path.append(os.getcwd())

from src.data.database import get_db_engine
from src.data.models import Base, User, SubscriptionPlan, LLMUsageLog
from src.repositories.usage_repository import UsageRepository

# Load .env if exists
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

def check_usage(target_user_id: str = "system"):
    """
    Utility to inspect current LLM usage and quotas for the current user.
    """
    print(f"\n{'='*60}")
    print(f"🔍 LLM Usage Monitoring - User: {target_user_id}")
    print(f"{'='*60}\n")

    try:
        # v4.2.1: Try to determine the best engine. 
        # If running locally without Docker, try SQLite fallback.
        try:
            engine = get_db_engine()
            # Test connection
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
        except Exception:
            db_path = "data/portfolio.db"
            print(f"⚠️ Postgres unreachable. Falling back to local SQLite: {db_path}")
            engine = get_db_engine(db_path=db_path)

        # v4.2.1: Ensure all tables exist (including subscription_plans)
        Base.metadata.create_all(engine)

        # v4.2.2: SCHEMA PATCH FOR LEGACY SQLITE
        # If the users table existed before Phase 16, it lacks subscription_id.
        if "sqlite" in str(engine.url):
            with engine.connect() as conn:
                try:
                    conn.execute(text("SELECT subscription_id FROM users LIMIT 1"))
                except Exception:
                    print("🛠️ Patching legacy SQLite schema: Adding users.subscription_id and users.current_billing_cycle_start")
                    conn.execute(text("ALTER TABLE users ADD COLUMN subscription_id TEXT"))
                    conn.execute(text("ALTER TABLE users ADD COLUMN current_billing_cycle_start TIMESTAMP"))
                    conn.commit()

        Session = sessionmaker(bind=engine)
        session = Session()
        usage_repo = UsageRepository(engine=engine)

        # 1. Fetch User & Plan
        user = session.query(User).filter_by(id=target_user_id).first()
        if not user:
            # Fallback: Find the first user in the DB
            user = session.query(User).first()
            if user:
                print(f"ℹ️ User '{target_user_id}' not found. Falling back to first user: {user.id}")
                target_user_id = user.id
            else:
                print(f"❌ No users found in database.")
                return

        plan = session.query(SubscriptionPlan).filter_by(id=user.subscription_id).first()
        if not plan:
            print(f"⚠️ User has no explicit subscription. Defaults to Free tier rules (nano, fast).")
            plan_name = "Default (Free?)"
            allowed_tiers = ["nano", "fast"]
            usd_limit = 0.0
        else:
            plan_name = plan.name
            allowed_tiers = plan.allowed_tiers or ["nano", "fast"]
            usd_limit = float(plan.monthly_usd_limit or 0.0)

        # 2. Calculate Usage
        since = user.current_billing_cycle_start or datetime(2026, 1, 1)
        current_cost = usage_repo.get_user_cycle_cost(target_user_id, since)

        # 3. Print Results
        print(f"👤 Account Status:")
        print(f"   - Plan:         {plan_name}")
        print(f"   - Cycle Start:  {since.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"   - Allowed:      {', '.join(allowed_tiers)}")
        
        print(f"\n💰 Financial Status:")
        limit_str = f"${usd_limit:.2f}" if usd_limit > 0 else "No Limit"
        usage_pct = (current_cost / usd_limit * 100) if usd_limit > 0 else 0
        
        status_icon = "🟢" if usage_pct < 80 else "🟡" if usage_pct < 100 else "🔴"
        print(f"   - Total Spend:  ${current_cost:.4f}")
        print(f"   - Quota Limit:  {limit_str}")
        print(f"   - Usage level:  {status_icon} {usage_pct:.1f}%")

        # 4. Recent Logs
        print(f"\n📜 Recent 10 Calls:")
        print(f"   {'Date (UTC)':<20} | {'Tier':<8} | {'Agent':<15} | {'Cost ($)':<10}")
        print(f"   {'-'*60}")
        
        recent_logs = session.query(LLMUsageLog).filter_by(user_id=target_user_id)\
            .order_by(LLMUsageLog.created_at.desc()).limit(10).all()
        
        if not recent_logs:
            print("   (No logs found for this user)")
        else:
            for log in recent_logs:
                date_str = log.created_at.strftime('%Y-%m-%d %H:%M')
                print(f"   {date_str:<20} | {log.tier:<8} | {log.agent_name[:15]:<15} | ${log.total_cost_usd:.6f}")

    except Exception as e:
        print(f"❌ Error retrieving usage data: {e}")
    finally:
        session.close()
        print(f"\n{'='*60}\n")

if __name__ == "__main__":
    # Get user_id from args or default to system
    import sys as _sys
    uid = _sys.argv[1] if len(_sys.argv) > 1 else "system"
    check_usage(uid)
