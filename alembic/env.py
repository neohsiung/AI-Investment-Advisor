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

# 2026-08-13: this used to hold a `_RUNTIME_MANAGED_TABLES` filter hiding the
# five tables that the repositories create at runtime with
# `CREATE TABLE IF NOT EXISTS` (ticker_universe, ticker_research,
# target_allocations, ticker_universe_logs, agent_performance). The filter
# existed because autogenerate reflected them out of the live database, found
# no matching model, and emitted a drop_table for each — but it bought that at
# the price its own comment named: those tables were outside migration control,
# so changing their DDL in the repositories could never be caught by CI.
#
# They now have ORM models (src/data/models.py) and migration 018, so the
# filter is gone and CI compares them like every other table.
#
# 2026-08-13：原本這裡有 `_RUNTIME_MANAGED_TABLES` 過濾器，把五張由 repository
# 在 runtime 建立的表排除在比對之外，代價是改動其 DDL 永遠不會被 CI 攔到。
# 這五張表已補上 ORM model 與 migration 018，故移除過濾器，改由 CI 一併比對。


def include_name(name, type_, parent_names):
    """No tables are excluded from autogenerate comparison."""
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
