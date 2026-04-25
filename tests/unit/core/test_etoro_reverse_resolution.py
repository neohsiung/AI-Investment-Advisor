import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from src.services.etoro_service import EtoroService
from src.domain.trading import Order, OrderAction

@pytest.fixture
def etoro_service():
    with patch('src.repositories.transaction_repository.AlchemyTransactionRepository', return_value=MagicMock()), \
         patch('src.infrastructure.risk_manager.RiskManager', return_value=MagicMock()):
        service = EtoroService(api_key="test_api", user_key="test_user")
        service.base_url = "https://public-api.etoro.com/api/v1"
        return service

@pytest.mark.asyncio
async def test_get_positions_with_reverse_resolution(etoro_service):
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
    
    with patch.object(etoro_service, '_fetch_portfolio_raw', new_callable=AsyncMock, return_value=mock_portfolio), \
         patch('httpx.AsyncClient.get', new_callable=AsyncMock) as mock_get:
        
        # Configure mock_get to return metadata when called
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_metadata
        mock_get.return_value = mock_response
        
        # Initial State: ID 888 is unknown
        etoro_service._id_to_symbol = {} 
        etoro_service._id_cache = {}    
        
        # Action
        positions = await etoro_service.get_positions()
        
        # Verification
        assert len(positions) == 1
        assert positions[0].symbol == "VTI.US" 
        assert positions[0].position_id == "1001"
        assert etoro_service._id_to_symbol["888"] == "VTI.US"
        assert etoro_service._id_cache["VTI"] == 888 

@pytest.mark.asyncio
async def test_execute_order_sell_vti_with_resolved_position(etoro_service):
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
    
    mock_metadata = {
        "instrumentDisplayDatas": [
            {"instrumentID": 888, "symbolFull": "VTI.US"}
        ]
    }

    # Use a more explicit mock for httpx.AsyncClient.get
    async def mock_httpx_get(client_self, url, **kwargs):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        if "portfolio" in str(url):
            mock_resp.json.return_value = mock_portfolio
        elif "instruments" in str(url):
            mock_resp.json.return_value = mock_metadata
        else:
            mock_resp.json.return_value = {} # Dict, not list
        return mock_resp

    with patch('httpx.AsyncClient.get', autospec=True, side_effect=mock_httpx_get), \
         patch('httpx.AsyncClient.post', new_callable=AsyncMock) as mock_post, \
         patch.object(etoro_service, '_notify_trade', new_callable=AsyncMock): # Disable notifications
        
        # Reset state to force resolution
        etoro_service._id_to_symbol = {}
        etoro_service._id_cache = {}
        
        # Mocking to avoid real network/logic depth
        with patch.object(etoro_service.risk_manager, 'check_constraints', return_value=True), \
             patch.object(etoro_service, 'get_history', new_callable=AsyncMock, return_value=[]), \
             patch.object(etoro_service, '_fetch_portfolio_raw', new_callable=AsyncMock, return_value=mock_portfolio):
            
            order = Order(symbol="VTI", quantity=1.0, action=OrderAction.SELL)
            
            mock_post_resp = MagicMock()
            mock_post_resp.status_code = 200
            mock_post_resp.json.return_value = {"OrderId": 555}
            mock_post.return_value = mock_post_resp
            
            result = await etoro_service.execute_order(order)
            
            assert result.get("OrderId") == 555
            
            # Verify trade execution call
            mock_post.assert_called_once()
            call_args = mock_post.call_args_list[0]
            # When patched on a class method, the first arg might be the instance if we used autospec=True
            # But httpx.AsyncClient.post is usually patched directly.
            actual_url = str(call_args[0][0]) if call_args[0] else str(call_args[1].get('url', ''))
            assert "1001" in actual_url
            assert "close-orders" in actual_url
