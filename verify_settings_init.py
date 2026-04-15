import os
import sys
import uuid
import json

# Force SQLite for verification
if not os.path.exists("data"):
    os.makedirs("data")
os.environ["DB_URL"] = "sqlite:///data/portfolio.db"

def verify_migration():
    from src.services.settings_service import SettingsService
    from src.repositories.settings_repository import AlchemySettingsRepository
    from src.data.database import init_db, get_db_engine
    
    # 1. Initialize DB if needed
    init_db()
    
    test_user_id = f"test-val-{str(uuid.uuid4())[:8]}"
    print(f"Testing initialization for NEW UUID: {test_user_id}")
    
    # Manually ensure user exists to avoid FK constraint
    from sqlalchemy import text
    engine = get_db_engine()
    with engine.begin() as conn:
        conn.execute(text("INSERT OR IGNORE INTO users (id, email) VALUES (:id, :email)"), {"id": test_user_id, "email": f"{test_user_id}@test.com"})

    service = SettingsService(user_id=test_user_id)
    
    # 2. Trigger initialization
    service.initialize_user_settings()
    
    # 3. Verify results
    settings = service.get_all_settings()
    
    print("\nVerified Settings found:")
    for k, v in settings.items():
        print(f" - {k}: {v}")
    
    required_keys = ["auto_trade_threshold", "risk_profile", "AI_MODEL", "DISPLAY_TIMEZONE"]
    missing = [k for k in required_keys if k not in settings]
    
    if not missing:
        print("\n✅ [PASSED] User settings successfully initialized and seeded.")
    else:
        print(f"\n❌ [FAILED] Missing keys: {missing}")
        sys.exit(1)

if __name__ == "__main__":
    try:
        verify_migration()
    except Exception as e:
        print(f"Error during verification: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
