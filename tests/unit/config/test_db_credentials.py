"""
Missing DB_PASS must fail loudly, never fall back to a default password.
缺 DB_PASS 時要明確失敗，不能退回預設密碼。
"""
import pytest

from src.config.db_credentials import MissingDbPasswordError, require_db_password


@pytest.fixture
def no_db_env(monkeypatch):
    for name in ("DB_URL", "DB_PASS", "DB_PASSWORD", "DATABASE_URL", "PGPASSWORD"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("DB_HOST", "db.invalid")
    return monkeypatch


def test_missing_password_raises_and_names_the_variable(no_db_env):
    with pytest.raises(MissingDbPasswordError, match="DB_PASS"):
        require_db_password()


def test_empty_password_counts_as_missing(no_db_env):
    no_db_env.setenv("DB_PASS", "")
    with pytest.raises(MissingDbPasswordError):
        require_db_password()


def test_returns_configured_password(no_db_env):
    no_db_env.setenv("DB_PASS", "from-env")
    assert require_db_password() == "from-env"


def test_legacy_variable_name_is_still_read(no_db_env):
    no_db_env.setenv("DB_PASSWORD", "legacy")
    assert require_db_password() == "legacy"


def test_sync_engine_builder_does_not_use_a_default_password(no_db_env):
    from src.data.database import get_db_engine

    with pytest.raises(MissingDbPasswordError):
        get_db_engine()


def test_async_engine_builder_does_not_use_a_default_password(no_db_env):
    from src.data import database

    with pytest.raises(MissingDbPasswordError):
        database.get_async_db_engine()


def test_llama_index_url_does_not_use_a_default_password(no_db_env):
    from src.services.llama_index_service import LlamaIndexService

    with pytest.raises(MissingDbPasswordError):
        LlamaIndexService._default_db_url()
