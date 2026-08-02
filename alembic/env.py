import os
from logging.config import fileConfig

from sqlalchemy import engine_from_config
from sqlalchemy import pool

from alembic import context

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# v5.3: Override sqlalchemy.url with environment variable if present
db_url = os.getenv("DB_URL")
if not db_url:
    db_user = os.getenv("DB_USER", "postgres")
    db_pass = os.getenv("DB_PASS", "postgres")
    db_host = os.getenv("DB_HOST", "postgres")
    db_port = os.getenv("DB_PORT", "5432")
    db_name = os.getenv("DB_NAME", "advisor_prod") # Fix default to advisor_prod
    db_url = f"postgresql+psycopg2://{db_user}:{db_pass}@{db_host}:{db_port}/{db_name}"

config.set_main_option("sqlalchemy.url", db_url)

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# add your model's MetaData object here
# for 'autogenerate' support
from src.data.models import Base
target_metadata = Base.metadata

# Tables created by application code at runtime, deliberately outside both the
# ORM and the migration chain. Without this filter autogenerate reflects them
# out of a live database, finds no matching model, and emits a drop_table —
# which makes `alembic check` fail against production even though nothing is
# actually wrong.
#
# Note what this does NOT buy us: these tables stay outside migration control,
# so editing their DDL in the repositories below will not be caught by CI.
# Promoting them into the chain is a separate refactor.
#
# 這些表由應用程式在 runtime 建立，刻意不在 ORM 也不在 migration 鏈裡。
# 沒有這個過濾器，autogenerate 會從實際資料庫反射到它們、找不到對應 model，
# 於是產生 drop_table，讓 `alembic check` 對 production 直接失敗。
# 代價：它們仍不受 migration 管控，改動其 DDL 不會被 CI 攔到。
_RUNTIME_MANAGED_TABLES = {
    # src/repositories/ticker_universe_repository.py:25,46,68,83
    "ticker_universe",
    "ticker_research",
    "target_allocations",
    "ticker_universe_logs",
    # src/repositories/agent_repository.py:52
    "agent_performance",
}


def include_name(name, type_, parent_names):
    """Keep runtime-created tables out of autogenerate comparisons."""
    if type_ == "table":
        return name not in _RUNTIME_MANAGED_TABLES
    return True

# other values from the config, defined by the needs of env.py,
# can be acquired:
# my_important_option = config.get_main_option("my_important_option")
# ... etc.


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        include_name=include_name,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.

    """
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            include_name=include_name,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
