import os
import logging
import uuid
from datetime import datetime, date
from src.data.database import get_db_engine, init_db
from src.repositories.transaction_repository import TransactionRepositoryImpl
from src.repositories.settings_repository import AlchemySettingsRepository
from src.repositories.verification_repository import AlchemyVerificationRepository
from src.infrastructure.memory.memory_manager import HybridMemory

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def verify_unification():
    """
    Verifies that all unified database components work with the current engine.
    """
    logger.info("🚀 Starting database unification verification...")
    
    # 1. Initialize
    init_db()
    engine = get_db_engine()
    is_sqlite = 'sqlite' in str(engine.url)
    logger.info(f"📡 Testing against: {'SQLite' if is_sqlite else 'PostgreSQL'}")
    
    user_id = "00000000-0000-0000-0000-000000000000" if not is_sqlite else "test_user"
    
    try:
        # 2. Test Settings
        logger.info("📝 Testing SettingsRepository...")
        settings_repo = AlchemySettingsRepository(engine=engine)
        settings_repo.set(user_id, "test_key", {"nested": "value", "score": 95})
        val = settings_repo.get(user_id, "test_key")
        assert val["nested"] == "value"
        logger.info("   ✅ Settings OK")

        # 3. Test Transactions
        logger.info("💰 Testing TransactionRepository...")
        trans_repo = TransactionRepositoryImpl(engine=engine)
        trans_repo.add(user_id, "AAPL", str(date.today()), "BUY", 10.5, 150.25, 1.0)
        all_trans = trans_repo.get_all_by_user(user_id)
        assert len(all_trans) > 0
        logger.info("   ✅ Transactions OK")

        # 4. Test Memory (Semantic Search)
        logger.info("🧠 Testing HybridMemory (pgvector/sqlite-vec)...")
        memory = HybridMemory(engine=engine)
        memory.add_memory(user_id, "The price of AAPL is high today.", [0.1]*1536, {"source": "test"})
        results = memory.search(user_id, "AAPL", [0.11]*1536, limit=1)
        assert len(results) > 0
        assert "AAPL" in results[0]["content"]
        logger.info("   ✅ Memory OK")

        # 5. Test Verification
        logger.info("🔑 Testing AlchemyVerificationRepository...")
        verify_repo = AlchemyVerificationRepository(engine=engine)
        verify_repo.create_verification(user_id, "matrix", "@user:matrix.org", "123456", datetime.now())
        v = verify_repo.get_by_user_id(user_id, "matrix")
        assert v["code"] == "123456"
        logger.info("   ✅ Verification OK")

        logger.info("\n✨ DEPLOYMENT READY: All database components successfully verified with v4.0 schema.")
        
    except Exception as e:
        logger.error(f"\n❌ VERIFICATION FAILED: {e}")
        raise

if __name__ == "__main__":
    verify_unification()
