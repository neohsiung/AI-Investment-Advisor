import pytest
import sqlite3
import os
from src.database import init_db, get_db_connection

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
        'transactions', 'positions', 'cash_flows', 'recommendations', 
        'reports', 'daily_snapshots', 'scheduler_logs', 'settings', 'prompt_history'
    ]
    
    for table in expected_tables:
        assert table in table_names
    
    conn.close()

def test_get_db_connection(tmp_path):
    db_path = tmp_path / "test_conn.db"
    
    # Should create parent dir if not exists
    nested_path = db_path / "nested" / "db.sqlite"
    
    conn = get_db_connection(nested_path)
    assert nested_path.exists()
    assert isinstance(conn, sqlite3.Connection)
    conn.close()
