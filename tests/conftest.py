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

        # decision_outcomes still has to be created by hand here. Note that
        # src/data/database.py's init_db() is a hand-written DDL script and
        # does NOT call Base.metadata.create_all() — so the declaration-only
        # ORM model added in 2026-08 (for `alembic check`) does not reach this
        # test database. scripts/init_db.py, the deployment path, DOES use
        # create_all() and is covered by that model.
        #
        # It matters because TradingProtectionsService fails CLOSED on a query
        # error, so a missing table hard-blocks every BUY in tests that
        # exercise the real protection path rather than silently no-op'ing.
        #
        # src/data/database.py 的 init_db() 是手寫 DDL、不呼叫 create_all()，
        # 所以新加的 ORM model 到不了測試資料庫（部署用的 scripts/init_db.py
        # 才走 create_all()）。TradingProtectionsService 查詢失敗是 fail-closed，
        # 缺表會直接擋掉 BUY，因此這段必須留著。
        from sqlalchemy import text
        with engine.begin() as conn:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS decision_outcomes (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    session_id TEXT,
                    agent_name TEXT NOT NULL,
                    ticker TEXT NOT NULL,
                    signal TEXT NOT NULL,
                    price_at_decision NUMERIC(18, 8) NOT NULL,
                    decided_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    horizon_days INTEGER NOT NULL DEFAULT 5,
                    resolved_at DATETIME,
                    realized_return_pct NUMERIC(10, 4),
                    benchmark_return_pct NUMERIC(10, 4),
                    alpha_pct NUMERIC(10, 4),
                    lesson TEXT,
                    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
            """))
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_decision_outcomes_user_id ON decision_outcomes (user_id)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_decision_outcomes_ticker ON decision_outcomes (ticker)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_decision_outcomes_pending ON decision_outcomes (resolved_at, decided_at)"))
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
