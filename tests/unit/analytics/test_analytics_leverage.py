import pytest
from src.services.analytics_service import LeverageCalculator
from unittest.mock import MagicMock

def test_calculate_metrics_with_leverage():
    """
    Verify that NLV is calculated based on Equity (Market Value / Leverage), 
    not Nominal Value.
    """
    mock_repo = MagicMock()
    # Scenario: 
    # META: Qty 1, Price 100, Leverage 5.0 -> Nominal 500, Equity 20
    # GOOG: Qty 1, Price 100, Leverage 1.0 -> Nominal 100, Equity 100
    mock_repo.get_leverage_summary.return_value = [
        ('META', 1.0, 5.0),
        ('GOOG', 1.0, 1.0)
    ]
    mock_repo.get_cash_balance.return_value = 100.0
    
    calc = LeverageCalculator(user_id='user_123', repository=mock_repo)
    prices = {'META': 100.0, 'GOOG': 100.0}
    
    metrics = calc.calculate_metrics(prices, 'user_123')
    
    # Calculation:
    # Portfolio Equity = (100*1/5) + (100*1/1) = 20 + 100 = 120
    # NLV = Cash (100) + Portfolio Equity (120) = 220
    # TNV (Gross) = |100*1*5| + |100*1*1| = 500 + 100 = 600
    # Leverage Ratio = 600 / 220 = 2.727
    
    assert metrics['nlv'] == pytest.approx(220.0)
    assert metrics['tnv'] == pytest.approx(600.0)
    assert metrics['cash_balance'] == 100.0
    assert metrics['leverage_ratio'] == pytest.approx(600 / 220)

def test_calculate_metrics_zero_qty():
    mock_repo = MagicMock()
    mock_repo.get_leverage_summary.return_value = [('AAPL', 0.0, 1.0)]
    mock_repo.get_cash_balance.return_value = 50.0
    
    calc = LeverageCalculator(user_id='user_123', repository=mock_repo)
    metrics = calc.calculate_metrics({'AAPL': 150.0}, 'user_123')
    
    assert metrics['nlv'] == 50.0
    assert metrics['tnv'] == 0.0
