import pytest
import sqlite3
import os
from src.data.database import init_db, get_db_connection

def test_init_db(tmp_path):
    db_path = tmp_path / "test_portfolio.db"
    init_db(str(db_path))

    assert db_path.exists()

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Check tables exist
    tables = cursor.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    table_names = [t[0] for t in tables]

    expected_tables = [
        'users', 'transactions', 'memory_embeddings', 'settings',
        'council_minutes', 'event_logs', 'reports', 'schema_version',
        'user_identities', 'daily_snapshots', 'cash_flows', 'risk_keywords',
        'channel_verifications'
    ]

    for table in expected_tables:
        assert table in table_names

    conn.close()

def test_get_db_connection(tmp_path):
    # get_db_connection returns a SQLAlchemy Session (not a raw connection).
    # The parent directory should be created, but the SQLite file is only
    # created after the first SQL execution (lazy creation by SQLite).
    nested_path = tmp_path / "nested" / "subdir" / "db.sqlite"

    conn = get_db_connection(str(nested_path))
    # Verify parent directory was created
    assert nested_path.parent.exists()
    # Verify the returned object is a valid SQLAlchemy Session
    assert conn is not None
    assert hasattr(conn, 'execute')
    conn.close()
