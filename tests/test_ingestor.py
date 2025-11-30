import pytest
import pandas as pd
from src.ingestor import TradeIngestor
from src.database import init_db, get_db_connection
import os

# 測試用 CSV 內容
ROBINHOOD_CSV_CONTENT = """state,symbol,date,side,quantity,price,fees
filled,AAPL,2023-01-01T10:00:00Z,buy,10,150.0,0.5
filled,GOOGL,2023-01-02T11:00:00Z,sell,5,2800.0,1.0
cancelled,MSFT,2023-01-03T12:00:00Z,buy,10,300.0,0.0
"""

@pytest.fixture
def setup_db_and_csv(tmp_path):
    """建立暫時資料庫與 CSV"""
    # 設定暫時 DB 路徑 (需修改 src.database.DB_PATH 或透過參數傳遞，這裡簡化為直接測試邏輯)
    # 由於 src.database 使用全域變數，這裡我們直接測試 ingestor 邏輯，
    # 實際專案應使用依賴注入或環境變數來切換 DB 路徑。
    
    # 建立測試 CSV
    csv_path = tmp_path / "robinhood_test.csv"
    csv_path.write_text(ROBINHOOD_CSV_CONTENT)
    
    return csv_path

def test_robinhood_ingestion(setup_db_and_csv):
    csv_path = setup_db_and_csv
    db_path = csv_path.parent / "test_portfolio.db"
    
    # 初始化暫存 DB
    init_db(db_path)
    
    ingestor = TradeIngestor(db_path=db_path)
    try:
        ingestor.ingest_csv(str(csv_path), broker="robinhood")
    except Exception as e:
        pytest.fail(f"Ingestion failed: {e}")

    # 驗證數據寫入
    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM transactions WHERE source_file=?", (csv_path.name,))
    rows = cursor.fetchall()
    
    # 應有 2 筆 (filled)，cancelled 應被過濾
    assert len(rows) == 2
    assert rows[0]['ticker'] == 'AAPL'
    assert rows[0]['quantity'] == 10.0
    
    conn.close()

# IBKR 測試數據
IBKR_CSV_CONTENT = """Type,Symbol,Date/Time,Quantity,T. Price,Comm/Fee,Amount
Trade,NVDA,2023-02-01T10:00:00Z,10,200.0,-1.0,-2001.0
Trade,TSLA,2023-02-02T11:00:00Z,-5,180.0,-1.0,899.0
Dividend,AAPL,2023-02-15T00:00:00Z,0,0,0,15.5
"""

def test_ibkr_ingestion(tmp_path):
    csv_path = tmp_path / "ibkr_test.csv"
    csv_path.write_text(IBKR_CSV_CONTENT)
    db_path = tmp_path / "test_portfolio_ibkr.db"
    
    init_db(db_path)
    ingestor = TradeIngestor(db_path=db_path)
    
    try:
        ingestor.ingest_csv(str(csv_path), broker="ibkr")
    except Exception as e:
        pytest.fail(f"IBKR Ingestion failed: {e}")
        
    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    
    # 檢查交易
    cursor.execute("SELECT * FROM transactions WHERE ticker='NVDA'")
    row = cursor.fetchone()
    assert row is not None
    assert row['action'] == 'BUY'
    assert row['quantity'] == 10.0
    
    cursor.execute("SELECT * FROM transactions WHERE ticker='TSLA'")
    row = cursor.fetchone()
    assert row['action'] == 'SELL'
    assert row['quantity'] == 5.0
    
    # 檢查股息
    cursor.execute("SELECT * FROM cash_flows WHERE type='DIVIDEND'")
    row = cursor.fetchone()
    assert row is not None
    assert row['amount'] == 15.5
    assert "AAPL" in row['description']
    
    conn.close()

def test_simple_ticker_ingestion(tmp_path):
    csv_path = tmp_path / "simple_test.csv"
    csv_path.write_text("ticker\nAAPL\nMSFT")
    db_path = tmp_path / "test_portfolio_simple.db"
    
    init_db(db_path)
    ingestor = TradeIngestor(db_path=db_path)
    
    try:
        ingestor.ingest_csv(str(csv_path), broker="simple")
    except Exception as e:
        pytest.fail(f"Simple Ingestion failed: {e}")
        
    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    
    cursor.execute("SELECT * FROM transactions WHERE ticker='AAPL'")
    row = cursor.fetchone()
    assert row is not None
    assert row['action'] == 'WATCH'
    assert row['quantity'] == 0.0
    
    conn.close()
