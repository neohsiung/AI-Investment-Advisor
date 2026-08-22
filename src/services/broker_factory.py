
import os
import threading
from datetime import datetime
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

def effective_trading_mode(user_id: str, settings_repo: Any = None) -> str:
    """
    Report whether orders for this user would hit real money. "real" | "demo".
    回報此使用者的委託是否會動用真實資金。

    Added 2026-08-10 so callers outside broker construction — notably the
    strategy-validation gate in AutomatedTradingService — can ask the question
    without building a broker or duplicating the override rules. Mirrors the
    resolution order used by get_broker() below: the stored `etoro_mode`
    (defaulting to "demo" when absent), with TRADING_MODE=paper forcing demo.

    2026-08-10 新增，讓 broker 建構之外的呼叫端（主要是策略驗證關卡）能在不建立
    broker、也不重複覆寫規則的前提下取得答案。解析順序與 get_broker() 一致。
    """
    repo = settings_repo or AlchemySettingsRepository()
    try:
        mode = repo.get(user_id, "etoro_mode") or "demo"
    except Exception as e:
        # Fail safe, not fail useful: if the mode cannot be read, treat it as
        # real so anything gated on "is this live?" errs toward caution.
        # 讀不到模式時一律視為實盤，讓以此為條件的防護傾向保守。
        logger.warning(f"effective_trading_mode: settings read failed ({e}); assuming 'real'")
        return "real"

    mode = str(mode).strip().lower()
    if _global_trading_mode() == "paper" and mode != "demo":
        return "demo"
    return mode


# Settings that decide how an eToro broker is built. Watched as a group so a
# rotation of either credential, a mode flip, or a base-URL change all move the
# change token below.
# 決定 eToro broker 如何建構的設定；整組監看，任一變動都會改變下方的變更權杖。
_ETORO_WATCHED_KEYS = (
    "etoro_api_key", "etoro_user_key", "etoro_mode",
    "etoro_api_base_url", "etoro_base_url",
)


class BrokerFactory:
    """
    Factory service to provide the preferred or enabled broker instances.
    Broker 工廠服務，提供首選或已啟用的證券商實例。
    """
    # Cache slot: cache_key -> (change_token, broker_instance).
    # 2026-08-02: previously a plain cache_key -> instance dict with NO
    # invalidation, so a credential or mode change never took effect until the
    # process restarted. Eviction hooks alone can't fix that — api, worker_1,
    # worker_2 and beat are separate processes with separate caches, and the
    # settings write path was fire-and-forget. Instead the entry carries a
    # token derived from the config it was built from and is rebuilt whenever
    # that token changes; correct by construction in every process, no
    # cross-process coordination needed.
    # 2026-08-02：改為攜帶變更權杖，設定一變就重建，免跨 process 協調。
    _instances: Dict[str, Tuple[str, IBroker]] = {}
    _lock = threading.RLock()

    @staticmethod
    def _change_token(
        broker_type: str,
        public_parts: Dict[str, Any],
        stamps: Optional[Dict[str, Optional[datetime]]] = None,
    ) -> str:
        """
        Cache-invalidation token, built ONLY from non-sensitive config values
        and the `settings.updated_at` of the rows that hold the sensitive ones.
        No credential is hashed, stored, or otherwise derived from here.

        Why timestamps work: `Setting.updated_at` carries `onupdate=func.now()`,
        and both write paths (`set` / `set_many`) go through ORM attribute
        assignment, so rotating a credential bumps its row. Writing the same
        value back leaves the row clean and does NOT bump — which is correct,
        the config genuinely didn't change. A deleted row is covered by the
        "∅" sentinel, since a deletion bumps nothing.

        This replaces a SHA-256 of the credentials themselves. That hash was
        never stored or logged, only compared — but feeding a secret into a
        fast hash is a pattern that shouldn't need auditing to be understood as
        safe, and static analysis flags it (py/weak-sensitive-data-hashing).
        The timestamps carry the same signal with nothing sensitive in them.

        Caveat for tests: SQLite renders `func.now()` as CURRENT_TIMESTAMP with
        one-second resolution, so two writes to the same key inside one second
        won't move the token. Tests asserting invalidation should call
        `BrokerFactory.invalidate()` instead. Postgres uses microsecond-
        resolution transaction time, so production is unaffected.

        變更權杖：只由非敏感設定值與敏感設定所在列的 updated_at 組成，絕不觸碰
        憑證本身。原本是對憑證做 SHA-256（僅比對、不記錄），但把秘密送進快速
        雜湊本就不該需要稽核才能確認安全，靜態分析也會標記。
        """
        public = "|".join(f"{k}={public_parts[k]!s}" for k in sorted(public_parts))
        if not stamps:
            return f"{broker_type}|{public}"
        marks = "|".join(
            f"{k}@{stamps[k].isoformat() if stamps.get(k) else '∅'}"
            for k in sorted(stamps)
        )
        return f"{broker_type}|{public}|{marks}"

    @staticmethod
    def invalidate(user_id: str = None, broker_type: str = None) -> int:
        """
        Drop cached brokers. Belt-and-braces alongside the change-token check —
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

        # 2. Read config FIRST, then compare its change token against the cache.
        #    Reading before the cache check is what makes staleness impossible.
        if broker_type == "ibkr":
            from src.services.ibkr_service import IBKRService
            host = settings_repo.get(user_id, "ibkr_host") or "127.0.0.1"
            port = int(settings_repo.get(user_id, "ibkr_port") or 7497)
            # Neither value is sensitive, so they go into the token directly —
            # no timestamps needed.
            token = BrokerFactory._change_token("ibkr", {"host": host, "port": port})
            build = lambda: IBKRService(host=host, port=port)

        elif broker_type == "etoro":
            # One batched read for the whole watched group: values to build
            # with, updated_at stamps to invalidate on. Replaces four separate
            # get() calls, so this is a round-trip cheaper than before.
            # 一次批次讀取整組：值用來建構，updated_at 用來失效；比原本四次
            # 個別 get() 還少一趟。
            watched = settings_repo.get_many_with_meta(user_id, _ETORO_WATCHED_KEYS)
            api_key = watched["etoro_api_key"][0]
            user_key = watched["etoro_user_key"][0]
            # 2026-08-02: fail-safe default flipped "real" → "demo". A missing
            # etoro_mode setting must never mean live money. This aligns with the
            # seed default (settings_service.initialize_user_settings) and
            # mem0_integration, which already default to "demo"; broker_factory
            # was the sole outlier.
            # 2026-08-02：預設值由 "real" 改為 "demo"。設定缺漏時絕不應等同真實下單。
            mode = watched["etoro_mode"][0] or "demo"
            global_mode = _global_trading_mode()
            if global_mode == "paper" and mode != "demo":
                logger.warning(
                    f"TRADING_MODE=paper overrides per-user etoro_mode={mode!r} for user {user_id} — forcing demo."
                )
                mode = "demo"
            # Load tenant-specific base URL from database
            # 從資料庫載入租戶專屬的 API 基底網址
            base_url = watched["etoro_api_base_url"][0] or watched["etoro_base_url"][0]
            # The token carries the POST-override mode, so flipping
            # TRADING_MODE invalidates too. Credentials contribute only through
            # their rows' updated_at — the values themselves never enter it.
            # 權杖用的是覆寫後的 mode，所以 TRADING_MODE 一翻也會失效；憑證只
            # 透過其列的 updated_at 參與，值本身不進權杖。
            token = BrokerFactory._change_token(
                "etoro",
                {"mode": mode, "base_url": base_url},
                {k: watched[k][1] for k in _ETORO_WATCHED_KEYS},
            )
            build = lambda: EtoroService(
                base_url=base_url, mode=mode, api_key=api_key,
                user_key=user_key, user_id=user_id,
            )

        else:
            logger.warning(f"Unknown broker type '{broker_type}', defaulting to Etoro")
            token = BrokerFactory._change_token("fallback", {"user": user_id})
            build = lambda: EtoroService(user_id=user_id)

        # 3. Serve from cache only when the config change token still matches.
        with BrokerFactory._lock:
            cached = BrokerFactory._instances.get(cache_key)
            if cached is not None and cached[0] == token:
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
            BrokerFactory._instances[cache_key] = (token, instance)
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
