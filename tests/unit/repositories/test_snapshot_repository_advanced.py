import pytest
from src.repositories.snapshot_repository import AlchemySnapshotRepository
from datetime import date
import os

@pytest.fixture
def repo():
    # Use in-memory SQLite for testing to avoid lock issues
    from sqlalchemy import create_engine
    engine = create_engine("sqlite:///:memory:")
    
    from src.data.database import init_db
    init_db(engine=engine)
    
    return AlchemySnapshotRepository(engine=engine)

def test_save_and_retrieve_extended_fields(repo):
    user_id = "test_user"
    today = date.today().strftime("%Y-%m-%d")
    
    # Save with extended fields
    repo.save_snapshot(
        user_id=user_id,
        date=today,
        nlv=100000.0,
        cash_balance=10000.0,
        invested_capital=90000.0,
        pnl=1000.0,
        total_tnv=110000.0,
        leverage_ratio=1.1,
        conviction_level=8.5,
        time_horizon="12 Months"
    )
    
    # Retrieve
    latest = repo.get_latest_by_user(user_id)
    assert latest is not None
    assert latest["conviction_level"] == 8.5
    assert latest["time_horizon"] == "12 Months"
    
    # Verify via history DataFrame
    df = repo.get_history_by_user(user_id)
    assert not df.empty
    assert "conviction_level" in df.columns
    assert df.iloc[0]["conviction_level"] == 8.5
    assert df.iloc[0]["time_horizon"] == "12 Months"

def test_upsert_behavior(repo):
    user_id = "test_user"
    today = "2024-01-01"
    
    repo.save_snapshot(user_id, today, 100, 10, 90, 0, 100, 1.0, 5.0, "Short")
    repo.save_snapshot(user_id, today, 200, 20, 180, 0, 200, 1.0, 9.0, "Long")
    
    latest = repo.get_latest_by_user(user_id)
    assert latest["total_nlv"] == 200
    assert latest["conviction_level"] == 9.0
    assert latest["time_horizon"] == "Long"
