import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from src.services.etoro_service import EtoroService
from src.domain.trading import Order, OrderAction

@pytest.fixture
def etoro_service():
    with patch('src.repositories.transaction_repository.AlchemyTransactionRepository', return_value=MagicMock()), \
         patch('src.infrastructure.risk_manager.RiskManager', return_value=MagicMock()):
        service = EtoroService(api_key="test_api", user_key="test_user", user_id="test_user")
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
    驗證 execute_order 能透過反向查找找到並關閉倉位。
    """
    from src.domain.trading import Position

    # Create a mock position that matches "VTI" via symbol "VTI.US"
    mock_position = Position(
        symbol="VTI.US",
        quantity=10.0,
        open_price=200.0,
        current_price=210.0,
        market_value=2100.0,
        unrealized_pnl=100.0,
        position_id="1001"
    )

    mock_post_resp = MagicMock()
    mock_post_resp.status_code = 200
    mock_post_resp.json.return_value = {"orderForOpen": {"statusID": 2, "orderID": 555}}
    mock_post_resp.raise_for_status = MagicMock()  # No-op

    # Mock at service method level for robustness across Python versions
    with patch.object(etoro_service.risk_manager, 'check_constraints', return_value=True), \
         patch.object(etoro_service, 'get_history', new_callable=AsyncMock, return_value=[]), \
         patch.object(etoro_service, 'get_positions', new_callable=AsyncMock, return_value=[mock_position]), \
         patch.object(etoro_service, '_fetch_portfolio_raw', new_callable=AsyncMock, return_value={}), \
         patch.object(etoro_service, '_resolve_instrument_id', new_callable=AsyncMock, return_value=888), \
         patch.object(etoro_service, '_notify_trade', new_callable=AsyncMock):

        # Patch httpx.AsyncClient to intercept the POST call inside execute_order
        mock_client = AsyncMock()
        mock_client.post.return_value = mock_post_resp
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch('httpx.AsyncClient', return_value=mock_client):
            order = Order(symbol="VTI", quantity=1.0, action=OrderAction.SELL)
            result = await etoro_service.execute_order(order)

            assert result.get("order_id") == "555"

            # Verify trade execution call
            mock_client.post.assert_called_once()
            call_args = mock_client.post.call_args
            actual_url = str(call_args[0][0]) if call_args[0] else str(call_args[1].get('url', ''))
            assert "1001" in actual_url
            assert "close-orders" in actual_url

