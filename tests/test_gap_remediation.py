import pytest
import pandas as pd
import tempfile
import os
import sqlite3
from src.data.ingestors import IngestorFactory
from src.data.ingestors.base import BaseIngestor
import pandas as pd
from datetime import datetime
from src.services.hr_service import HRService
from src.utils.cache import ResponseCache

# --- Test IngestorFactory ---

def test_ingestor_factory_creates_correct_instance():
    # Test Simple
    ingestor = IngestorFactory.get_ingestor("Simple", "dummy.db")
    assert isinstance(ingestor, BaseIngestor)
    assert ingestor.__class__.__name__ == "SimpleIngestor"

    # Test Robinhood
    ingestor = IngestorFactory.get_ingestor("Robinhood", "dummy.db")
    assert ingestor.__class__.__name__ == "RobinhoodIngestor"

    # Test IBKR
    ingestor = IngestorFactory.get_ingestor("IBKR", "dummy.db")
    assert ingestor.__class__.__name__ == "IBKRIngestor"

    # Test Invalid
    with pytest.raises(ValueError):
        IngestorFactory.get_ingestor("Unknown", "dummy.db")

# --- Test HRService ---

@pytest.fixture
def mock_cache_db():
    # Create a temp DB
    fd, path = tempfile.mkstemp()
    os.close(fd)
    
    # Init schema
    conn = sqlite3.connect(path)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS response_cache (
            key TEXT PRIMARY KEY,
            agent_name TEXT,
            response TEXT,
            timestamp DATETIME
        )
    """)
    conn.commit()
    conn.close()
    
    yield path
    os.remove(path)

def test_hr_service_health_check(mock_cache_db):
    # Insert mock data
    conn = sqlite3.connect(mock_cache_db)
    cursor = conn.cursor()
    
    # 1. Active Agent (Active now)
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute("INSERT INTO response_cache (key, agent_name, timestamp) VALUES (?, ?, ?)", 
                   ("key1", "Momentum", now_str))
    
    # 2. Zombie Agent (Active 10 days ago)
    old_date = datetime(2023, 1, 1).strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute("INSERT INTO response_cache (key, agent_name, timestamp) VALUES (?, ?, ?)", 
                   ("key2", "Fundamental", old_date))
    
    conn.commit()
    conn.close()
    
    service = HRService(db_path=mock_cache_db)
    df = service.check_agent_health()
    
    print(df)
    
    # Verify Momentum is Active
    momentum = df[df['Agent'] == 'Momentum'].iloc[0]
    assert "Active" in momentum['Status']
    
    # Verify Fundamental is Zombie
    fundamental = df[df['Agent'] == 'Fundamental'].iloc[0]
    assert "Zombie" in momentum['Status'] or "Zombie" in fundamental['Status']
    
    # Verify Unknown Agent is "Missing" (default behavior)
    # CIO is in known list but not in DB
    cio = df[df['Agent'] == 'CIO'].iloc[0]
    assert "Missing" in cio['Status']
