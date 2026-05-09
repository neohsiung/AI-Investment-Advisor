#!/usr/bin/env python3
"""Production DB initializer.

Strategy:
  1. If alembic_version table does NOT exist → fresh database.
     • Use Base.metadata.create_all(checkfirst=True) to create the
       schema directly from ORM models.
     • Then `alembic stamp head` so Alembic considers all migrations applied.
  2. If alembic_version table DOES exist → existing database.
     • Run `alembic upgrade head` normally to apply any pending migrations.

This avoids the chicken-and-egg problem where auto-generated migrations
assume a specific intermediate schema state that doesn't match a fresh DB
created by the baseline migration chain.
"""
import os
import sys
import subprocess

from sqlalchemy import create_engine, inspect, text


def get_database_url() -> str:
    """Build DATABASE_URL from env vars (matches alembic/env.py logic)."""
    url = os.getenv("DB_URL")
    if url:
        return url

    user = os.getenv("DB_USER", "postgres")
    password = os.getenv("DB_PASS", "postgres")
    host = os.getenv("DB_HOST", "postgres")
    port = os.getenv("DB_PORT", "5432")
    name = os.getenv("DB_NAME", "advisor_prod")
    return f"postgresql+psycopg2://{user}:{password}@{host}:{port}/{name}"


def main():
    db_url = get_database_url()
    engine = create_engine(db_url)

    inspector = inspect(engine)
    has_alembic = "alembic_version" in inspector.get_table_names()

    if has_alembic:
        # Existing DB: apply any pending migrations normally
        print("[init_db] alembic_version found — running alembic upgrade head")
        result = subprocess.run(
            ["alembic", "upgrade", "head"],
            capture_output=False,
        )
        sys.exit(result.returncode)
    else:
        # Fresh DB: create schema from ORM models, then stamp
        print("[init_db] Fresh database detected — creating schema from ORM models")

        # Ensure pgvector extension exists
        with engine.begin() as conn:
            conn.execute(text('CREATE EXTENSION IF NOT EXISTS "uuid-ossp"'))
            conn.execute(text('CREATE EXTENSION IF NOT EXISTS "vector"'))

        # Import models AFTER engine is created (avoids import-time side effects)
        from src.data.models import Base  # noqa: E402

        Base.metadata.create_all(engine, checkfirst=True)
        print(f"[init_db] Created {len(Base.metadata.tables)} tables from ORM models")

        # Stamp alembic so future migrations start from head
        result = subprocess.run(
            ["alembic", "stamp", "head"],
            capture_output=False,
        )
        if result.returncode != 0:
            print("[init_db] WARNING: alembic stamp head failed, but tables are created")
        else:
            print("[init_db] Stamped alembic_version to head")

        sys.exit(0)


if __name__ == "__main__":
    main()
