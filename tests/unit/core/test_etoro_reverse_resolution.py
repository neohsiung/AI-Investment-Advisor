import pytest
from unittest.mock import MagicMock, patch
from src.services.etoro_service import EtoroService
from src.domain.trading import Order, OrderAction

@pytest.fixture
def etoro_service():
    with patch('src.repositories.transaction_repository.AlchemyTransactionRepository'), \
         patch('src.infrastructure.risk_manager.RiskManager'):
        service = EtoroService(api_key="test_api", user_key="test_user")
        service.base_url = "https://public-api.etoro.com/api/v1"
        return service

def test_get_positions_with_reverse_resolution(etoro_service):
    """
    Test that an unknown instrument ID in the portfolio is resolved via metadata API.
    """
    # 1. Mock Raw Portfolio with an unknown ID (888)
    mock_portfolio = {
        "clientPortfolio": {
            "positions": [
                {
                    "instrumentID": 888,
                    "positionId": "1001",
                    "units": 10.0,
                    "openRate": 200.0,
                    "currentRate": 210.0,
                    "unitsBaseValueDollars": 2100.0,
                    "netProfit": 100.0
                }
            ]
        }
    }
    
    # 2. Mock Metadata Response for ID 888
    mock_metadata = {
        "instrumentDisplayDatas": [
            {
                "instrumentID": 888,
                "symbolFull": "VTI.US",
                "instrumentDisplayName": "Vanguard Total Stock Market ETF"
            }
        ]
    }
    
    with patch.object(etoro_service, '_fetch_portfolio_raw', return_value=mock_portfolio), \
         patch('requests.get') as mock_get:
        
        # Configure mock_get to return metadata when called
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_metadata
        mock_get.return_value = mock_response
        
        # Initial State: ID 888 is unknown
        etoro_service._id_to_symbol = {} 
        etoro_service._id_cache = {}    
        
        # Action
        positions = etoro_service.get_positions()
        
        # Verification
        assert len(positions) == 1
        assert positions[0].symbol == "VTI.US" 
        assert positions[0].position_id == "1001"
        assert etoro_service._id_to_symbol["888"] == "VTI.US"
        assert etoro_service._id_cache["VTI"] == 888 

def test_execute_order_sell_vti_with_resolved_position(etoro_service):
    """
    Test that execute_order finds and closes a position resolved via reverse lookup.
    """
    # Mock data
    mock_portfolio = {
        "clientPortfolio": {
            "positions": [
                {
                    "instrumentID": 888,
                    "positionId": "1001",
                    "units": 10.0,
                    "openRate": 200.0,
                    "currentRate": 210.0,
                    "unitsBaseValueDollars": 2100.0,
                    "netProfit": 100.0
                }
            ]
        }
    }
    
    # Enable metadata mock side effect
    def mock_get_side_effect(url, **kwargs):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        if "portfolio" in url:
            mock_resp.json.return_value = mock_portfolio
        elif "instruments" in url:
            mock_resp.json.return_value = {
                "instrumentDisplayDatas": [
                    {"instrumentID": 888, "symbolFull": "VTI.US"}
                ]
            }
        else:
            mock_resp.json.return_value = []
        return mock_resp

    with patch('requests.get', side_effect=mock_get_side_effect), \
         patch('requests.post') as mock_post, \
         patch.object(etoro_service, '_notify_trade'): # Disable notifications to avoid extra post calls
        
        # Reset state to force resolution
        etoro_service._id_to_symbol = {}
        etoro_service._id_cache = {}
        
        # Risk Manager mock
        with patch.object(etoro_service.risk_manager, 'check_constraints', return_value=True), \
             patch.object(etoro_service, 'get_history', return_value=[]):
            
            order = Order(symbol="VTI", quantity=1.0, action=OrderAction.SELL)
            
            mock_post_resp = MagicMock()
            mock_post_resp.status_code = 200
            mock_post_resp.json.return_value = {"OrderId": 555}
            mock_post.return_value = mock_post_resp
            
            result = etoro_service.execute_order(order)
            
            assert result.get("OrderId") == 555
            
            # Verify trade execution call
            # We expect exactly one POST call now because notifications are disabled
            mock_post.assert_called_once()
            actual_url = str(mock_post.call_args[0][0])
            assert "1001" in actual_url
            assert "close-orders" in actual_url
