import pytest
import json
from src.refinement import RefinementEngine
from src.database import init_db, get_db_connection
from sqlalchemy import text

@pytest.fixture
def setup_refinement_db(tmp_path):
    db_path = tmp_path / "test_refinement.db"
    config_path = tmp_path / "test_config.json"
    init_db(db_path)
    return db_path, config_path

def test_refinement_logic(setup_refinement_db):
    db_path, config_path = setup_refinement_db
    
    engine = RefinementEngine(db_path=db_path, config_path=config_path)
    
    # 1. 記錄建議 (BUY @ 100)
    engine.record_recommendation("MOMENTUM", "TEST", "BUY", 100.0)
    
    # 驗證寫入
    conn = get_db_connection(db_path)
    # Use explicit column selection to avoid mapping issues
    result = conn.execute(text("SELECT outcome_score FROM recommendations WHERE ticker='TEST'"))
    rec = result.fetchone()
    assert rec is not None
    assert rec[0] == 0
    conn.close()
    
    # 2. 執行分析 (假設當前價格 110 > 100*1.05 -> Score should be 1)
    # RefinementEngine 的 run_attribution_analysis 中 mock 了 current_price = price * 1.1
    engine.run_attribution_analysis()
    
    # 驗證分數更新
    conn = get_db_connection(db_path)
    result = conn.execute(text("SELECT outcome_score FROM recommendations WHERE ticker='TEST'"))
    rec = result.fetchone()
    assert rec[0] == 1
    conn.close()
    
    # 驗證 Config 更新
    with open(config_path, 'r') as f:
        config = json.load(f)
    assert config["MOMENTUM"]["weight"] == 1.1
