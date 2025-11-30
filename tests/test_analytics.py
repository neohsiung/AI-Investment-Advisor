import pytest
from src.analytics import LeverageCalculator, ROIEngine
from src.database import init_db, get_db_connection
import uuid

@pytest.fixture
def setup_db(tmp_path):
    db_path = tmp_path / "test_analytics.db"
    init_db(db_path)
    return db_path

def test_leverage_calculation(setup_db):
    conn = get_db_connection(setup_db)
    cursor = conn.cursor()
    
    # 1. 入金 10,000
    cursor.execute("INSERT INTO cash_flows (id, date, amount, type) VALUES (?, ?, ?, ?)",
                   (str(uuid.uuid4()), "2023-01-01", 10000, "DEPOSIT"))
    
    # 2. 買入 AAPL: 100股 @ 150 (Cost 15,000) -> 使用 5,000 融資 (假設)
    # Cash Impact: -15,000. Cash Balance = 10,000 - 15,000 = -5,000 (負債)
    cursor.execute('''
        INSERT INTO transactions (id, ticker, trade_date, action, quantity, price, amount)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', (str(uuid.uuid4()), "AAPL", "2023-01-02", "BUY", 100, 150, 15000))
    
    conn.commit()
    conn.close()
    
    calc = LeverageCalculator(db_path=setup_db)
    
    # 情境 A: 股價不變 (150)
    # Portfolio Value = 100 * 150 = 15,000
    # Cash Balance = -5,000
    # NLV = 15,000 + (-5,000) = 10,000
    # TNV = 15,000
    # Leverage = 15,000 / 10,000 = 1.5
    
    metrics = calc.calculate_metrics({"AAPL": 150})
    assert metrics['tnv'] == 15000
    assert metrics['nlv'] == 10000
    assert metrics['leverage_ratio'] == 1.5
    
    # 情境 B: 股價上漲至 200
    # Portfolio Value = 100 * 200 = 20,000
    # NLV = 20,000 - 5,000 = 15,000
    # TNV = 20,000
    # Leverage = 20,000 / 15,000 = 1.33
    
    metrics = calc.calculate_metrics({"AAPL": 200})
    assert metrics['tnv'] == 20000
    assert metrics['nlv'] == 15000
    assert abs(metrics['leverage_ratio'] - 1.333) < 0.01

def test_roi_calculation(setup_db):
    conn = get_db_connection(setup_db)
    cursor = conn.cursor()
    
    # 入金 10,000
    cursor.execute("INSERT INTO cash_flows (id, date, amount, type) VALUES (?, ?, ?, ?)",
                   (str(uuid.uuid4()), "2023-01-01", 10000, "DEPOSIT"))
    conn.commit()
    conn.close()
    
    engine = ROIEngine(db_path=setup_db)
    
    # 情境: NLV 變為 12,000 (獲利 2,000)
    # ROI = (12,000 - 10,000) / 10,000 = 20%
    roi = engine.calculate_roi(nlv=12000)
    assert roi == 20.0
    
    # 情境: 虧損至 8,000
    # ROI = (8,000 - 10,000) / 10,000 = -20%
    roi = engine.calculate_roi(nlv=8000)
    assert roi == -20.0
