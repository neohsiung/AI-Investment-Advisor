
from typing import Dict, Any, Optional
from src.domain.broker import IBroker
from src.repositories.settings_repository import AlchemySettingsRepository
from src.services.etoro_service import EtoroService
from src.utils.logger import setup_logger
logger = setup_logger("BrokerFactory")

class BrokerFactory:
    """
    Factory service to provide the preferred or enabled broker instances.
    Broker 工廠服務，提供首選或已啟用的證券商實例。
    """
    _instances: Dict[str, IBroker] = {}

    @staticmethod
    def get_broker(user_id: str, broker_type: str = None) -> IBroker:
        """
        Get a specific broker instance based on type or user preference.
        根據類型或使用者偏好獲取特定證券商實例。
        """
        settings_repo = AlchemySettingsRepository()
        
        # 1. Determine Broker Type
        if not broker_type:
            broker_type = settings_repo.get(user_id, "preferred_broker") or "etoro"
        
        broker_type = broker_type.lower()
        
        # 2. Return cached instance or create new
        if broker_type in BrokerFactory._instances:
            return BrokerFactory._instances[broker_type]
            
        logger.info(f"Initializing Broker: {broker_type}")
        
        if broker_type == "ibkr":
            from src.services.ibkr_service import IBKRService
            host = settings_repo.get(user_id, "ibkr_host") or "127.0.0.1"
            port = int(settings_repo.get(user_id, "ibkr_port") or 7497)
            instance = IBKRService(host=host, port=port)
            
        elif broker_type == "etoro":
            api_key = settings_repo.get(user_id, "etoro_api_key")
            user_key = settings_repo.get(user_id, "etoro_user_key")
            mode = settings_repo.get(user_id, "etoro_mode") or "real"
            instance = EtoroService(mode=mode, api_key=api_key, user_key=user_key)
            
        else:
            logger.warning(f"Unknown broker type '{broker_type}', defaulting to Etoro")
            instance = EtoroService()
            
        BrokerFactory._instances[broker_type] = instance
        return instance

    @staticmethod
    def get_enabled_brokers(user_id: str) -> Dict[str, IBroker]:
        """
        Retrieve all enabled brokers for a user based on database settings.
        根據資料庫設定檢索使用者所有已啟用的證券商。
        """
        settings_repo = AlchemySettingsRepository()
        brokers = {}
        
        # Check Etoro
        raw_enable_etoro = settings_repo.get(user_id, "enable_etoro")
        etoro_enabled = raw_enable_etoro is True or str(raw_enable_etoro).lower() in ("true", "1")
        if etoro_enabled:
            try:
                brokers["etoro"] = BrokerFactory.get_broker(user_id, "etoro")
            except Exception as e:
                logger.warning(f"Failed to init etoro: {e}")
        elif raw_enable_etoro is None:
            import os
            if os.getenv("ETORO_API_KEY"):
                brokers["etoro"] = BrokerFactory.get_broker(user_id, "etoro")


        # Check IBKR
        if settings_repo.get(user_id, "enable_ibkr") == "true":
             try:
                 brokers["ibkr"] = BrokerFactory.get_broker(user_id, "ibkr")
             except Exception: pass
             
        # FALLBACK: If nothing enabled (e.g. first run), enable Etoro
        if not brokers:
             # Default to etoro being enabled if nothing else is
             brokers["etoro"] = BrokerFactory.get_broker(user_id, "etoro")
                
        return brokers
