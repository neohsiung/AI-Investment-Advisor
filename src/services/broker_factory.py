
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
            host = settings_repo.get(user_id, "futu_host") or "127.0.0.1"
            port = int(settings_repo.get(user_id, "futu_port") or 11111)
            pwd = settings_repo.get(user_id, "futu_pwd")
            instance = FutuService(host=host, port=port, pwd=pwd)
            
        elif broker_type == "ibkr":
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
        Get all enabled brokers for a user.
        Checks settings (DB) first, falls back to Env Vars only if DB Not Configured?
        Actually, we moved full control to DB + Env fallback within Service.
        Here we strictly check DB 'enable_X' flags.
        """
        settings_repo = SqliteSettingsRepository()
        brokers = {}
        
        # Check Etoro
        if settings_repo.get(user_id, "enable_etoro") == "true":
            try:
                brokers["etoro"] = BrokerFactory.get_broker(user_id, "etoro")
            except Exception as e:
                logger.warning(f"Failed to init etoro: {e}")
        # Legacy Fallback: if not explicitly disabled in DB, and Env Vars exist, enable it?
        # User said "manage in settings". So if settings are empty, we might defaults.
        # But let's respect "enable_etoro" being None -> check env.
        elif settings_repo.get(user_id, "enable_etoro") is None:
             import os
             if os.getenv("ETORO_API_KEY"): 
                 brokers["etoro"] = BrokerFactory.get_broker(user_id, "etoro")

        # Check Futu
        if settings_repo.get(user_id, "enable_futu") == "true":
             try:
                 brokers["futu"] = BrokerFactory.get_broker(user_id, "futu")
             except: pass

        # Check IBKR
        if settings_repo.get(user_id, "enable_ibkr") == "true":
             try:
                 brokers["ibkr"] = BrokerFactory.get_broker(user_id, "ibkr")
             except: pass
             
        # FALLBACK: If nothing enabled (e.g. first run), enable Etoro
        if not brokers:
             # Default to etoro being enabled if nothing else is
             brokers["etoro"] = BrokerFactory.get_broker(user_id, "etoro")
                
        return brokers
