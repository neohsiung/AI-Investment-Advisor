
import hashlib
import json
import os
import threading
from typing import Dict, Any, Optional, Tuple
from src.domain.broker import IBroker
from src.repositories.settings_repository import AlchemySettingsRepository
from src.services.etoro_service import EtoroService
from src.utils.logger import setup_logger
logger = setup_logger("BrokerFactory")

# 2026-07-14 (open-source Phase 1 — self-host paper-mode default): a global,
# env-level override so a fresh self-host install never places real trades
# by accident. Deliberately opt-in via explicit env var, not a silent
# behavior change for existing deployments — if TRADING_MODE is unset,
# behavior is the per-user etoro_mode setting, which as of 2026-08-02
# defaults to "demo" when unset. Set TRADING_MODE=paper to force every
# broker into demo/paper mode regardless of stored per-user settings;
# TRADING_MODE=live is the explicit opt-in to real trading.
# self-host .env.example ships TRADING_MODE=paper.
def _global_trading_mode() -> Optional[str]:
    value = os.getenv("TRADING_MODE", "").strip().lower()
    if value in ("paper", "live"):
        return value
    if value:
        logger.warning(f"Unrecognized TRADING_MODE={value!r}, ignoring (expected 'paper' or 'live')")
    return None

class BrokerFactory:
    """
    Factory service to provide the preferred or enabled broker instances.
    Broker 工廠服務，提供首選或已啟用的證券商實例。
    """
    # Cache slot: cache_key -> (config_fingerprint, broker_instance).
    # 2026-08-02: previously a plain cache_key -> instance dict with NO
    # invalidation, so a credential or mode change never took effect until the
    # process restarted. Eviction hooks alone can't fix that — api, worker_1,
    # worker_2 and beat are separate processes with separate caches, and the
    # settings write path is fire-and-forget (BackgroundTasks). Instead the
    # entry carries a fingerprint of the config it was built from and is
    # rebuilt whenever that config changes; correct by construction in every
    # process, no cross-process coordination needed.
    # 2026-08-02：改為攜帶設定指紋，設定一變就重建，免跨 process 協調。
    _instances: Dict[str, Tuple[str, IBroker]] = {}
    _lock = threading.RLock()

    @staticmethod
    def _fingerprint(parts: Dict[str, Any]) -> str:
        """
        Stable hash of the config a broker was built from. Never logged, never
        returned — only compared. Hashing (not storing) keeps credentials out
        of the cache structure.
        設定指紋；只做比對，不記錄、不外流，避免憑證留在快取結構中。
        """
        canonical = json.dumps(parts, sort_keys=True, default=str)
        return hashlib.sha256(canonical.encode()).hexdigest()

    @staticmethod
    def invalidate(user_id: str = None, broker_type: str = None) -> int:
        """
        Drop cached brokers. Belt-and-braces alongside the fingerprint check —
        gives the settings write path and tests an explicit handle.
        Returns the number of slots removed.
        清除快取的 broker 實例；回傳清掉的筆數。
        """
        with BrokerFactory._lock:
            if user_id is None and broker_type is None:
                n = len(BrokerFactory._instances)
                BrokerFactory._instances.clear()
                return n
            doomed = [
                k for k in BrokerFactory._instances
                if (user_id is None or k.startswith(f"{user_id}_"))
                and (broker_type is None or k.endswith(f"_{broker_type.lower()}"))
            ]
            for k in doomed:
                del BrokerFactory._instances[k]
            return len(doomed)

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
        cache_key = f"{user_id}_{broker_type}"

        # 2. Read config FIRST, then compare its fingerprint against the cache.
        #    Reading before the cache check is what makes staleness impossible.
        if broker_type == "ibkr":
            from src.services.ibkr_service import IBKRService
            host = settings_repo.get(user_id, "ibkr_host") or "127.0.0.1"
            port = int(settings_repo.get(user_id, "ibkr_port") or 7497)
            fingerprint = BrokerFactory._fingerprint(
                {"t": "ibkr", "host": host, "port": port}
            )
            build = lambda: IBKRService(host=host, port=port)

        elif broker_type == "etoro":
            api_key = settings_repo.get(user_id, "etoro_api_key")
            user_key = settings_repo.get(user_id, "etoro_user_key")
            # 2026-08-02: fail-safe default flipped "real" → "demo". A missing
            # etoro_mode setting must never mean live money. This aligns with the
            # seed default (settings_service.initialize_user_settings) and
            # mem0_integration, which already default to "demo"; broker_factory
            # was the sole outlier.
            # 2026-08-02：預設值由 "real" 改為 "demo"。設定缺漏時絕不應等同真實下單。
            mode = settings_repo.get(user_id, "etoro_mode") or "demo"
            global_mode = _global_trading_mode()
            if global_mode == "paper" and mode != "demo":
                logger.warning(
                    f"TRADING_MODE=paper overrides per-user etoro_mode={mode!r} for user {user_id} — forcing demo."
                )
                mode = "demo"
            # Load tenant-specific base URL from database
            # 從資料庫載入租戶專屬的 API 基底網址
            base_url = settings_repo.get(user_id, "etoro_api_base_url") or settings_repo.get(user_id, "etoro_base_url")
            # Fingerprint uses the POST-override mode, so flipping TRADING_MODE
            # also invalidates. Credentials are hashed, never stored here.
            fingerprint = BrokerFactory._fingerprint({
                "t": "etoro", "api_key": api_key, "user_key": user_key,
                "mode": mode, "base_url": base_url,
            })
            build = lambda: EtoroService(
                base_url=base_url, mode=mode, api_key=api_key,
                user_key=user_key, user_id=user_id,
            )

        else:
            logger.warning(f"Unknown broker type '{broker_type}', defaulting to Etoro")
            fingerprint = BrokerFactory._fingerprint({"t": "fallback", "user": user_id})
            build = lambda: EtoroService(user_id=user_id)

        # 3. Serve from cache only when the config fingerprint still matches.
        with BrokerFactory._lock:
            cached = BrokerFactory._instances.get(cache_key)
            if cached is not None and cached[0] == fingerprint:
                return cached[1]

        # 4. Construct OUTSIDE the lock — EtoroService.__init__ does DB and file
        #    I/O, and holding a global lock through it would serialize every
        #    broker construction across the process.
        if cached is not None:
            logger.info(f"Broker config changed for user {user_id} ({broker_type}), rebuilding")
        else:
            logger.info(f"Initializing Broker: {broker_type} for user: {user_id}")
        instance = build()

        with BrokerFactory._lock:
            # Re-check: a concurrent caller may have won the race. Benign —
            # last writer wins, both instances are equivalent.
            BrokerFactory._instances[cache_key] = (fingerprint, instance)
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
