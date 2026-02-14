
from typing import Dict
from src.domain.broker import IBroker
from src.repositories.settings_repository import SqliteSettingsRepository
from src.services.etoro_service import EtoroService
from src.services.futu_service import FutuService
import logging

logger = logging.getLogger(__name__)

class BrokerFactory:
    """
    Factory to get the preferred broker instance.
    """
    _instances: Dict[str, IBroker] = {}

    @staticmethod
    def get_broker(user_id: str, broker_type: str = None) -> IBroker:
        settings_repo = SqliteSettingsRepository()
        
        # 1. Determine Broker Type
        if not broker_type:
            broker_type = settings_repo.get(user_id, "preferred_broker") or "etoro"
        
        broker_type = broker_type.lower()
        
        # 2. Return cached instance or create new
        if broker_type in BrokerFactory._instances:
            return BrokerFactory._instances[broker_type]
            
        logger.info(f"Initializing Broker: {broker_type}")
        
        if broker_type == "futu":
            instance = FutuService()
        elif broker_type == "ibkr":
            from src.services.ibkr_service import IBKRService
            instance = IBKRService()
        elif broker_type == "etoro":
            instance = EtoroService() # Default params
        else:
            logger.warning(f"Unknown broker type '{broker_type}', defaulting to Etoro")
            instance = EtoroService()
            
        BrokerFactory._instances[broker_type] = instance
        return instance

    @staticmethod
    def get_enabled_brokers(user_id: str) -> Dict[str, IBroker]:
        """
        Get all enabled brokers for a user.
        Currently assumes all implemented brokers are enabled if configured.
        """
        # In a real scenario, check DB for 'etoro_enabled', 'futu_enabled' etc.
        # For now, return all supported types.
        
        brokers = {}
        supported_types = ["etoro", "futu", "ibkr"]
        
        for b_type in supported_types:
            try:
                # Reuse get_broker logic which handles caching
                broker = BrokerFactory.get_broker(user_id, b_type)
                brokers[b_type] = broker
            except Exception as e:
                logger.warning(f"Failed to initialize broker {b_type}: {e}")
                
        return brokers
