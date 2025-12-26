import pytest
from unittest.mock import MagicMock, patch
from src.refinement import RefinementEngine
from src.domain.entities import SignalType

class MockRow:
    def __init__(self, data):
        self._data = data
        for k, v in data.items():
            setattr(self, k, v)
    
    def keys(self):
        return self._data.keys()

@pytest.fixture
def mock_db_connection():
    with patch("src.refinement.get_db_connection") as mock:
        yield mock

@pytest.fixture
def mock_market_data():
    with patch("src.refinement.MarketDataService") as mock:
        yield mock

@pytest.fixture
def mock_feedback_repo():
    with patch("src.refinement.SqliteFeedbackRepository") as mock:
        yield mock

def test_run_attribution_analysis(mock_db_connection, mock_market_data, mock_feedback_repo):
    # Setup Mocks
    mock_conn = MagicMock()
    mock_db_connection.return_value = mock_conn
    
    mock_md_instance = mock_market_data.return_value
    mock_md_instance.get_current_prices.return_value = {"AAPL": 160.0, "TSLA": 90.0} # AAPL +6.6%, TSLA -10%

    mock_repo_instance = mock_feedback_repo.return_value

    # Mock DB Recommendations
    # Rec 1: Buying AAPL at 150. Current 160 (+6.6%) -> Expect Score 1.0
    rec1 = MockRow({"id": "1", "date": "2023-01-01", "agent": "Momentum", "ticker": "AAPL", "signal": "BUY", "price_at_signal": 150.0})
    # Rec 2: Buying TSLA at 100. Current 90 (-10%) -> Expect Score -1.0
    rec2 = MockRow({"id": "2", "date": "2023-01-01", "agent": "Fundamental", "ticker": "TSLA", "signal": "BUY", "price_at_signal": 100.0})
    
    mock_conn.execute.return_value.fetchall.return_value = [rec1, rec2]

    # Initialize Engine
    engine = RefinementEngine()
    engine.run_attribution_analysis()

    # Validations
    # 1. Check get_current_prices called with correct tickers
    tickers_arg = mock_md_instance.get_current_prices.call_args[0][0]
    assert "AAPL" in tickers_arg
    assert "TSLA" in tickers_arg

    # 2. Check Valid Updates
    # conn.execute should be called for SELECT, then UPDATE x2
    assert mock_conn.execute.call_count >= 3
    
    # 3. Check Repository Save
    assert mock_repo_instance.save.call_count == 2
    
    # Inspect first save (AAPL)
    args, _ = mock_repo_instance.save.call_args_list[0]
    feedback_ex = args[0]
    assert feedback_ex.agent_name == "Momentum"
    assert feedback_ex.outcome_score == 1.0
    assert feedback_ex.signal == SignalType.BUY
    
    # Inspect second save (TSLA)
    args, _ = mock_repo_instance.save.call_args_list[1]
    feedback_ex = args[0]
    assert feedback_ex.agent_name == "Fundamental"
    assert feedback_ex.outcome_score == -1.0
