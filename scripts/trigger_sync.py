import os
import sys

sys.path.insert(0, '/workspace')

try:
    from src.services.etoro_service import EtoroService
    from src.repositories.transaction_repository import AlchemyTransactionRepository
    from src.data.database import get_db_engine
    
    engine = get_db_engine()
    service = EtoroService(user_id='90693c07-6177-42df-97d9-915f3ce7c573')
    
    user_id = '90693c07-6177-42df-97d9-915f3ce7c573'

    print("Running eToro sync_history to recalibrate Cash...")
    result = service.sync_history(user_id=user_id, days=10) # 10 days to cover past
    print(f"Sync complete. Added: {result.get('added')}, Skipped: {result.get('skipped')}")
        
except Exception as e:
    import traceback
    traceback.print_exc()
