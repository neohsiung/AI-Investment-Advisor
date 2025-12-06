
import pytest
from unittest.mock import MagicMock, patch, mock_open
import pandas as pd
from src.ingestor import TradeIngestor
from src.analytics import LeverageCalculator, SnapshotRecorder

# --- Ingestor Tests ---

def test_ingestor_csv_missing_columns():
    ingestor = TradeIngestor(":memory:")
    # Create valid CSV content but missing required columns
    csv_content = "Symbol,Date,Amount\nAAPL,2023-01-01,100" 
    
    with patch("builtins.open", mock_open(read_data=csv_content)), \
         patch("pathlib.Path.exists", return_value=True):
         
        with patch("pandas.read_csv", return_value=pd.DataFrame({"Symbol": ["AAPL"], "Date": ["2023-01-01"], "Amount": [100]})):
             # The Simple broker parser raises ValueError if 'ticker' is missing.
             with pytest.raises(ValueError, match="ticker"):
                ingestor.ingest_csv("dummy.csv", broker="Simple")

def test_ingestor_unsupported_broker():
    ingestor = TradeIngestor(":memory:")
    with patch("pathlib.Path.exists", return_value=True):
        with pytest.raises(ValueError):
            ingestor.ingest_csv("dummy.csv", broker="UnknownBroker")

def test_ingestor_manual_trade_error():
    ingestor = TradeIngestor(":memory:")
    with patch("src.ingestor.get_db_connection", side_effect=Exception("DB connection failed")):
        with pytest.raises(Exception):
            ingestor.ingest_manual_trade("AAPL", "2023-01-01", "BUY", 10, 150, 0)


# --- Analytics Tests ---

def test_leverage_calculator_empty():
    calc = LeverageCalculator(":memory:")
    # calculate_metrics returns a dict
    with patch("pandas.read_sql", return_value=pd.DataFrame()):
        # Mock cash flow sum
        with patch("src.analytics.get_db_connection") as mock_conn:
             mock_conn.return_value.execute.return_value.fetchone.return_value = [0.0]
             metrics = calc.calculate_metrics({})
             assert metrics['leverage_ratio'] == 0.0 or metrics['tnv'] == 0.0

def test_leverage_calculator_error():
    calc = LeverageCalculator(":memory:")
    with patch("src.analytics.get_db_connection", side_effect=Exception("DB Error")):
        with pytest.raises(Exception):
            calc.calculate_metrics({})

def test_snapshot_recorder_run():
    recorder = SnapshotRecorder(":memory:")
    # SnapshotRecorder.record_daily_snapshot(nlv, cash_balance)
    with patch("src.analytics.get_db_connection") as mock_conn:
         # Mock return for invested capital query
         mock_conn.return_value.execute.return_value.fetchone.return_value = [5000.0]
         
         recorder.record_daily_snapshot(nlv=10000.0, cash_balance=2000.0)
         
         # Verification: Should execute REPLACE INTO daily_snapshots
         mock_conn.return_value.execute.assert_called()


# --- SystemEngineerAgent Tests ---
from src.agents.engineer import SystemEngineerAgent

@pytest.fixture
def mock_engineer_agent():
    with patch("builtins.open", mock_open(read_data="System Prompt")):
        with patch("src.agents.base_agent.BaseAgent._load_config", return_value={"provider": "OpenAI"}):
            # SystemEngineerAgent sets name and prompt_path internally
            agent = SystemEngineerAgent() 
            return agent

def test_engineer_get_schedule_config(mock_engineer_agent):
    # This method reads from DB, not LLM
    with patch("src.agents.engineer.get_db_connection") as mock_conn:
        # Mock conn.execute().fetchall()
        mock_result = MagicMock()
        # Return tuples to match row[0], row[1] access
        mock_result.fetchall.return_value = [
            ("schedule_daily", "12:00"),
            ("schedule_weekly", "02:00")
        ]
        mock_conn.return_value.execute.return_value = mock_result
    
        config = mock_engineer_agent.get_schedule_config()
        assert config["schedule_daily"] == "12:00"
    assert config["schedule_weekly"] == "02:00" # Default value

def test_engineer_analyze_optimization_needs(mock_engineer_agent):
    cio_report = "Some report... \nSystem Optimization Feedback\n Please optimize Momentum Agent."
    needs = mock_engineer_agent.analyze_optimization_needs(cio_report)
    assert len(needs) == 1
    assert "Please optimize Momentum Agent" in needs[0]["raw_feedback"]

def test_engineer_analyze_optimization_needs_none(mock_engineer_agent):
    cio_report = "Report with no feedback."
    needs = mock_engineer_agent.analyze_optimization_needs(cio_report)
    assert len(needs) == 0

def test_ingestor_robinhood(tmp_path):
    ingestor = TradeIngestor(":memory:")
    # Create dummy Robinhood CSV
    csv_file = tmp_path / "robinhood.csv"
    csv_content = "state,symbol,date,side,quantity,price,fees\nfilled,AAPL,2023-01-01,buy,10,150,0.02"
    csv_file.write_text(csv_content)
    
    # We don't need to patch open since we use real file on tmp_path, 
    # but ingestor checks file_path.exists(). tmp_path exists.
    
    with patch("src.ingestor.get_db_connection") as mock_conn:
        ingestor.ingest_csv(str(csv_file), broker="robinhood")
        mock_conn.return_value.cursor.return_value.execute.assert_called()

def test_ingestor_ibkr(tmp_path):
    ingestor = TradeIngestor(":memory:")
    # Create dummy IBKR CSV
    csv_file = tmp_path / "ibkr.csv"
    csv_content = "Type,Symbol,Date/Time,Quantity,T. Price,Comm/Fee\nTrade,AAPL,2023-01-01,10,150,-1.0\nDividend,AAPL,2023-01-02,0,0,5.0"
    csv_file.write_text(csv_content)
    
    with patch("src.ingestor.get_db_connection") as mock_conn:
        ingestor.ingest_csv(str(csv_file), broker="ibkr")
        # Should execute for Trade and Dividend
        assert mock_conn.return_value.cursor.return_value.execute.call_count >= 2


