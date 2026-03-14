import pytest
from unittest.mock import MagicMock, patch, ANY
import pandas as pd
from src.services.analytics_service import LeverageCalculator, SnapshotRecorder, update_daily_snapshot, ROIEngine, PnLCalculator, AnalyticsService

# Helpers for mocking repository returns

@pytest.fixture
def mock_trans_repo():
    with patch('src.services.analytics_service.AlchemyTransactionRepository') as MockRepo:
        repo = MockRepo.return_value
        yield repo

@pytest.fixture
def mock_snapshot_repo():
    with patch('src.services.analytics_service.AlchemySnapshotRepository') as MockRepo:
        repo = MockRepo.return_value
        yield repo

def test_leverage_calculator_metrics():
    # Setup Data
    holdings = [("AAPL", 10.0), ("SPY", 5.0)]
    current_prices = {"AAPL": 150.0, "SPY": 400.0}
    user_id = "user1"

    # Mock Repository
    mock_repo = MagicMock()
    # Mock Repository: Return (ticker, net_qty, avg_leverage)
    mock_repo.get_leverage_summary.return_value = [("AAPL", 10.0, 1.0), ("SPY", 5.0, 1.0)]
    mock_repo.get_cash_balance.return_value = 10000.0 # From cash flows table (Simulating Deposit)
    
    # Mock transactions for cash balance calculation logic
    # DEPOSIT in transactions should now be IGNORED by calculation
    t1 = MagicMock(); t1.action = 'DEPOSIT'; t1.amount = 10000.0
    mock_repo.get_all_by_user.return_value = [t1]

    calc = LeverageCalculator(user_id=user_id, repository=mock_repo)
    metrics = calc.calculate_metrics(current_prices, user_id)

    # Logic Check:
    # TNV = (10*150) + (5*400) = 1500 + 2000 = 3500
    # Cash Flow Sum (Direct) = 10000
    # Trans Cash Impact: DEPOSIT Ignored -> 0
    # Total Cash = 10000
    # NLV = 10000 + 3500 = 13500
    # Lev = 3500 / 13500 = 0.259...

    assert metrics['tnv'] == 3500.0
    assert metrics['cash_balance'] == 10000.0
    assert metrics['nlv'] == 13500.0
    assert 0.25 < metrics['leverage_ratio'] < 0.27

def test_snapshot_recorder():
    mock_trans_repo = MagicMock()
    mock_trans_repo.calculate_net_invested_capital.return_value = 5000.0
    
    # Patch the classes inside analytics_service to ensure SnapshotRecorder uses our mocks
    with patch('src.services.analytics_service.AlchemyTransactionRepository', return_value=mock_trans_repo), \
         patch('src.services.analytics_service.AlchemySnapshotRepository') as MockSnapRepo:
        
        recorder = SnapshotRecorder()
        recorder.record_daily_snapshot(nlv=10000.0, cash_balance=5000.0, user_id="user1", total_tnv=5000.0, leverage_ratio=0.5)
        
        # Verify save_snapshot called on snapshot repo
        MockSnapRepo.return_value.save_snapshot.assert_called_with(
            user_id="user1",
            date=ANY, # Any date string
            nlv=10000.0,
            cash_balance=5000.0,
            invested_capital=5000.0, # From trans repo
            pnl=5000.0, # 10000 - 5000
            total_tnv=5000.0,
            leverage_ratio=0.5
        )

def test_update_daily_snapshot_integration():
    # This function uses local variables for services, so we MUST patch the classes used.
    
    with patch('src.services.analytics_service.AlchemyTransactionRepository') as MockTransRepo, \
         patch('src.services.analytics_service.AlchemySnapshotRepository') as MockSnapRepo, \
         patch('src.services.analytics_service.MarketDataService') as MockMarket:
         
        # Setup
        MockTransRepo.return_value.get_active_tickers.return_value = ["AAPL"]
        # Mock get_leverage_summary and others needed by LeverageCalculator internally
        MockTransRepo.return_value.get_leverage_summary.return_value = [("AAPL", 5.0, 1.0)]
        MockTransRepo.return_value.get_cash_balance.return_value = 0.0
        MockTransRepo.return_value.get_all_by_user.return_value = [] # No transactions for cash impact
        MockTransRepo.return_value.calculate_net_invested_capital.return_value = 0.0
        
        MockMarket.return_value.get_current_prices.return_value = {"AAPL": 100.0}
        
        update_daily_snapshot("db.sqlite", "user1")
        
        # Verify
        MockTransRepo.return_value.get_active_tickers.assert_called_with("user1", None)
        MockMarket.return_value.get_current_prices.assert_called_with(["AAPL"])
        
        # Check if snapshot was saved
        # Note: update_daily_snapshot instantiates SnapshotRecorder, which instantiates AlchemySnapshotRepository
        MockSnapRepo.return_value.save_snapshot.assert_called()


def test_roi_engine():
    mock_repo = MagicMock()
    mock_repo.calculate_net_invested_capital.return_value = 5000.0
    
    engine = ROIEngine(user_id="user1", repository=mock_repo)
    roi = engine.calculate_roi(nlv=6000.0, user_id="user1")
    
    # ROI = (6000 - 5000) / 5000 = 0.20 = 20%
    assert roi == 20.0
    
    mock_repo.calculate_net_invested_capital.return_value = 0.0
    assert engine.calculate_roi(nlv=6000.0, user_id="user1") == 0.0

def test_pnl_calculator():
    mock_repo = MagicMock()
    
    # Mock Transactions
    t1 = MagicMock(); t1.ticker="AAPL"; t1.action="BUY"; t1.quantity=10.0; t1.price=100.0; t1.fees=0.0
    t2 = MagicMock(); t2.ticker="AAPL"; t2.action="SELL"; t2.quantity=5.0; t2.price=120.0; t2.fees=0.0
    t3 = MagicMock(); t3.ticker="GOOG"; t3.action="BUY"; t3.quantity=10.0; t3.price=200.0; t3.fees=0.0
    
    # Note: PnLCalculator now expects Reverse Order (Desc) from repo, and does list()[::-1]
    # So we provide them in DESC date order (newest first)
    mock_repo.get_all_by_user.return_value = [t3, t2, t1]
    
    calc = PnLCalculator(user_id="user1", repository=mock_repo)
    current_prices = {"AAPL": 130.0, "GOOG": 210.0}
    
    breakdown = calc.calculate_breakdown(current_prices, "user1")
    
    # Logic Verification (Same as before)
    # AAPL: Realized 100. Unrealized 150. Total 250.
    # GOOG: Unrealized 100.
    # Total: Realized 100. Unrealized 250. Total 350.
    
    assert breakdown['realized'] == 100.0
    assert breakdown['unrealized'] == 250.0
    assert breakdown['total'] == 350.0
    assert breakdown['details']['AAPL']['realized'] == 100.0
    assert breakdown['details']['AAPL']['unrealized'] == 150.0
