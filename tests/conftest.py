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

        # 2026-08-02: decision_outcomes is created only via Alembic migration
        # 007 (raw SQL) and has no ORM model, so init_db()'s create_all() never
        # makes it here. TradingProtectionsService now fails CLOSED on a query
        # error (see trading_protections_service.py), so the missing table
        # started hard-blocking every BUY in tests that exercise the real
        # protection path instead of silently no-op'ing.
        # decision_outcomes 只由 alembic migration 007 建（raw SQL，無 ORM
        # model），create_all() 建不到它。TradingProtectionsService 現在對
        # 查詢失敗 fail-closed，這個缺表洞會直接擋掉 BUY 而非靜默放行。
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
