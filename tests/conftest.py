import sys
from unittest.mock import MagicMock, patch
import pytest

# Import common shared fixtures to make them available globally
pytest_plugins = [
    "tests.fixtures.common_services",
    "tests.fixtures.sentinel_fixtures"
]

# Centralized Mocking to prevent decorator pollution and Protobuf conflicts
def pytest_configure(config):
    # This runs before any tests are collected or imported
    
    # Define the pass-through decorator
    def mock_cache_decorator(*args, **kwargs):
        def decorator(func):
            return func
        return decorator
    mock_cache_decorator.clear = MagicMock()

    # Mock Streamlit
    if "streamlit" not in sys.modules:
        mock_st = MagicMock()
        mock_st.cache_data = mock_cache_decorator
        mock_st.cache_resource = mock_cache_decorator
        
        # Mock columns to handle spec variations
        def mock_columns(spec):
            if isinstance(spec, int):
                return [MagicMock() for _ in range(spec)]
            elif isinstance(spec, (list, tuple)):
                return [MagicMock() for _ in range(len(spec))]
            return [MagicMock()]
        mock_st.columns.side_effect = mock_columns
        
        sys.modules["streamlit"] = mock_st
    else:
        # If already imported, force patch the decorators
        mock_st = sys.modules["streamlit"]
        try:
            mock_st.cache_data = mock_cache_decorator
            mock_st.cache_resource = mock_cache_decorator
        except Exception:
            # If it's a module that doesn't allow assignment, we might need a different approach
            # but usually sys.modules contains a mock or a real module we can patch
            pass

    # Mock other problematic modules
    problematic_modules = [
        "extra_streamlit_components",
        "plotly.express",
        "streamlit.components.v1",
        "streamlit.components.v1.components",
        "yfinance",
        "futu"
    ]
    for mod in problematic_modules:
        if mod not in sys.modules:
            mock_mod = MagicMock()
            if mod == "yfinance":
                # Ensure Ticker().fast_info.get() returns None to avoid truthy mock issues
                mock_mod.Ticker.return_value.fast_info = {}
                mock_mod.Ticker.return_value.info = {}
            elif mod == "futu":
                # Basic symbols for futu to avoid AttributeError in services
                from tests.mocks import futu as mock_futu_impl
                mock_mod = mock_futu_impl
            sys.modules[mod] = mock_mod

    # v4.2.1: Ensure Test Isolation (Database and Caching)
    # Patch environment variables to force SQLite in-memory and disable caching for unit tests
    import os
    os.environ["DB_TYPE"] = "sqlite"
    os.environ["DB_URL"] = "sqlite:///:memory:"
    os.environ["DISABLE_WORKFLOW_CACHE"] = "true"
    # v4.2.1: Ensure we are recognized as a test environment even during collection
    if "PYTEST_CURRENT_TEST" not in os.environ:
        os.environ["PYTEST_CURRENT_TEST"] = "collection"
        
    # pytest-xdist: isolate_redis below flushes the whole Redis DB between tests, so workers sharing DB 0 wipe each
    # other's keys mid-test (order:inflight locks vanished). Give every worker its own DB index; serial runs unchanged.
    # xdist 下 isolate_redis 會 flushdb，多個 worker 共用 DB 0 會互相清空；每個 worker 用自己的 DB index，單機串行不變。
    _worker = os.getenv("PYTEST_XDIST_WORKER", "")
    if _worker.startswith("gw") and _worker[2:].isdigit() and not os.getenv("REDIS_URL") and os.getenv("REDIS_HOST"):
        os.environ["REDIS_URL"] = (
            f"redis://{os.environ['REDIS_HOST']}:{os.getenv('REDIS_PORT', '6379')}/{int(_worker[2:]) % 16}")

    # Unset Postgres variables if they exist in .env to prevent leaky defaults
    for env_var in ["DB_HOST", "DB_USER", "DB_PASS", "DB_NAME"]:
        if env_var in os.environ:
            del os.environ[env_var]

    # v4.2.1: Ensure Database Schema is initialized for in-memory SQLite tests
    try:
        from src.data.database import init_db, get_db_engine
        import src.data.models # Ensure all models register with Base.metadata
        engine = get_db_engine()
        init_db(engine=engine, force=True)

        # The hand-created `decision_outcomes` table that used to live here is
        # gone. It existed because src/data/database.py's init_db() was a
        # hand-written DDL script that did not call Base.metadata.create_all(),
        # so an ORM-only model never reached the test database — and
        # TradingProtectionsService fails CLOSED on a query error, meaning a
        # missing table hard-blocked every BUY in tests.
        #
        # init_db() now create_all()s from the ORM, so every model reaches this
        # database automatically and the workaround has no reason to exist.
        #
        # 舊 init_db 是手寫 DDL、不呼叫 create_all，ORM-only 的 model 到不了測試庫，
        # 故需手動建表。現已改為 create_all，此變通不再需要。
    except Exception as e:
        print(f"DEBUG: Failed to initialize in-memory DB during collection: {e}")

@pytest.fixture
def mock_streamlit_module():
    """Fixture to provide access to the centralized Streamlit mock."""
    return sys.modules.get("streamlit")


@pytest.fixture(autouse=True)
def isolate_trading_mode(monkeypatch):
    """
    Keep TRADING_MODE out of the ambient environment for every test.
    讓每個測試都在沒有 TRADING_MODE 環境變數的狀態下執行。

    2026-08-10: prod's .env gained `TRADING_MODE=paper` as a global brake on
    live trading. That variable leaks into the test process and silently
    rewrote broker mode assertions — test_broker_cache_invalidation began
    asserting 'real' but seeing 'demo'. Tests that care about the override
    (e.g. test_trading_mode_paper_override_changes_token) set it explicitly,
    so unsetting it by default is both hermetic and closer to their intent.

    2026-08-10：prod 的 .env 新增了 TRADING_MODE=paper 作為實盤交易的全域煞車，
    該變數會滲入測試行程並默默改寫 broker 模式的斷言。需要此覆寫的測試會自行
    明確設定，因此預設清除它既能隔離環境，也更貼近測試原意。
    """
    monkeypatch.delenv("TRADING_MODE", raising=False)


@pytest.fixture(autouse=True)
def mock_build_config_chain():
    """
    Global test fixture: patch build_config_chain to return a MockLLMGateway candidate.
    In unit tests there is no DB tier binding, so without this every agent __init__
    raises ValueError("No model candidates configured in DB...").
    Production code stays strict (DB-only, Rule #13); this patch is test-only.
    """
    from src.infrastructure.llm.llm_gateway import MockLLMGateway
    from src.infrastructure.llm.resilient_pipeline import ModelCandidate

    def _mock_chain(user_id, tier, **kwargs):
        return [ModelCandidate(
            model_id="mock",
            provider_code="mock",
            model_code="mock-model",
            gateway_class=MockLLMGateway,
            base_url="",
            api_key="mock-key",
            max_retries=1,
            timeout_seconds=30.0,
        )]

    with patch(
        "src.infrastructure.llm.llm_config_chain.build_config_chain",
        side_effect=_mock_chain,
    ):
        yield


@pytest.fixture(autouse=True)
def isolate_quota_governor():
    """
    Keep external quota governor state hermetic across unit tests.
    外部配額控管器為單例模式，測試間重置避免跨測試之配額耗盡與頻率防抖洩漏。
    """
    try:
        from src.infrastructure.governance.quota_governor import ExternalQuotaGovernor
        ExternalQuotaGovernor.get_instance().reset()
    except Exception:
        pass
    yield
    try:
        from src.infrastructure.governance.quota_governor import ExternalQuotaGovernor
        ExternalQuotaGovernor.get_instance().reset()
    except Exception:
        pass


_REDIS_AVAILABLE = None


def _check_redis_available() -> bool:
    global _REDIS_AVAILABLE
    if _REDIS_AVAILABLE is not None:
        return _REDIS_AVAILABLE
    try:
        import os
        redis_host = os.getenv("REDIS_HOST", "localhost")
        redis_port = int(os.getenv("REDIS_PORT", "6379"))
        import redis
        client = redis.Redis(host=redis_host, port=redis_port, socket_connect_timeout=0.2)
        client.ping()
        _REDIS_AVAILABLE = True
    except Exception:
        _REDIS_AVAILABLE = False
    return _REDIS_AVAILABLE


@pytest.fixture(autouse=True)
def isolate_redis():
    """
    Keep Redis cache and state hermetic across unit tests.
    When a Redis server is available (e.g. CI service container), flush DB between tests.
    """
    if _check_redis_available():
        try:
            from src.infrastructure.cache.redis_client import get_redis_sync
            get_redis_sync().flushdb()
        except Exception:
            pass
    yield
    if _check_redis_available():
        try:
            from src.infrastructure.cache.redis_client import get_redis_sync
            get_redis_sync().flushdb()
        except Exception:
            pass



@pytest.fixture(autouse=True)
def ensure_current_event_loop():
    """
    Sync tests that call asyncio.get_event_loop() assumed an ambient loop left behind by an earlier async test in the
    same process; under pytest-xdist a worker may reach them first ("There is no current event loop"). Provide a
    private loop when none is usable and close it afterwards.
    同步測試呼叫 asyncio.get_event_loop() 時依賴前一個 async 測試遺留的 loop；xdist 下 worker 可能先跑到它們而失敗。
    沒有可用 loop 時提供私有 loop，測試後關閉。
    """
    import asyncio
    import warnings

    owned = None
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            loop = asyncio.get_event_loop_policy().get_event_loop()
        if loop.is_closed():
            raise RuntimeError("closed")
    except RuntimeError:
        owned = asyncio.new_event_loop()
        asyncio.set_event_loop(owned)
    yield
    if owned is not None and not owned.is_closed():
        owned.close()
        asyncio.set_event_loop(None)


@pytest.fixture(scope="session", autouse=True)
def warm_llm_provider_registry():
    """
    Load LLMGatewayFactory's registry and the provider catalog once per process, before any test patches `open` or
    `os.path.exists`. The first load is lazy and permanent: tests such as test_base_agent_coverage patch both while
    constructing an agent, which made the YAML read parse junk, cached an empty ProviderCatalog and left the registry at
    {'mock'} for the rest of that worker. Serially an earlier test always loaded it first; under pytest-xdist the
    worker's first test may be the patched one.
    在任何測試 patch open / os.path.exists 之前先載入一次。首次載入是延遲且永久的；被 patch 的測試若剛好是 worker 的第一個，
    會把空目錄與只有 mock 的 registry 固定下來。串行時總有更早的測試先載入，xdist 不保證。
    """
    try:
        from src.infrastructure.llm.llm_gateway import LLMGatewayFactory
        LLMGatewayFactory._ensure_loaded()
    except Exception as exc:  # never hide a broken registry: tests that need it will fail loudly
        print(f"WARN: could not warm LLM provider registry: {exc}")
    yield
