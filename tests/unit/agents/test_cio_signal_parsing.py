import pytest
from unittest.mock import MagicMock, patch
from src.services.workflow_service import DailyWorkflow

@pytest.fixture
def daily_workflow():
    # Mock repositories and services to avoid DB/API calls during init
    with patch('src.services.workflow_service.AlchemyTransactionRepository', return_value=MagicMock()), \
         patch('src.services.workflow_service.AlchemyMemoryRepository', return_value=MagicMock()), \
         patch('src.services.workflow_service.AgentLLMProvider', return_value=MagicMock()), \
         patch('src.services.workflow_service.PerformanceService', return_value=MagicMock()):
        workflow = DailyWorkflow(user_id="test_user")
        workflow.context = {
            'market_data': {
                'AAPL': {'price_data': {'close': 150.0}},
                'TSLA': {'price_data': {'close': 200.0}},
                'SPY': {'price_data': {'close': 400.0}}
            }
        }
        return workflow

async def test_parse_actionable_orders_table(daily_workflow):
    report = """
## 投資結論與執行建議 (Investment Conclusion & Actionable Orders)

| 代號 | 動作 | 數量 | 信心分數 | 理由 |
| :--- | :--- | :--- | :--- | :--- |
| AAPL | BUY | 10 | 9 | 強勁動能與財報利多 |
| TSLA | SELL | 5 | 7 | 短期技術指標過熱 |
| MSFT | HOLD | - | 5 | 觀望中 |
"""
    # Call the new specialized method directly
    await daily_workflow._parse_actionable_orders(report)
             
    assert "actionable_orders" in daily_workflow.context
    orders = daily_workflow.context['actionable_orders']
    
    assert len(orders) == 2 # AAPL and TSLA (MSFT is HOLD)
    
    # Check AAPL
    aapl = next(o for o in orders if o['ticker'] == 'AAPL')
    assert aapl['action'] == 'BUY'
    assert aapl['score'] == 9
    assert aapl['quantity'] == '10'
    assert "強勁動能" in aapl['reason']
    
    # Check TSLA
    tsla = next(o for o in orders if o['ticker'] == 'TSLA')
    assert tsla['action'] == 'SELL'
    assert tsla['score'] == 7
    assert "技術指標" in tsla['reason']

async def test_parse_quantity_percentage(daily_workflow):
    report = """
| 代號 | 動作 | 數量/比例 | 信心分數 | 理由 |
| :--- | :--- | :--- | :--- | :--- |
| NVDA | BUY | 5% | 8 | 輝達長期看好 |
"""
    await daily_workflow._parse_actionable_orders(report)
        
    orders = daily_workflow.context.get('actionable_orders', [])
    assert len(orders) == 1
    assert orders[0]['ticker'] == 'NVDA'
    assert orders[0]['quantity'] == '5%'
    assert orders[0]['score'] == 8
