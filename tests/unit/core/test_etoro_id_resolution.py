
import pytest
import asyncio
from unittest.mock import MagicMock, patch, AsyncMock
from src.services.etoro_service import EtoroService

@pytest.fixture
def mock_etoro_response():
    return {
        "InstrumentID": 1001,
        "SymbolFull": "AAPL",
        "InstrumentDisplayName": "Apple Inc."
    }

@pytest.mark.asyncio
async def test_resolve_instrument_id_cache(mock_etoro_response):
    """Verify caching logic avoids redundant API calls."""
    # Note: EtoroService._resolve_instrument_id calls _fetch_id_from_api (async)
    with patch.object(EtoroService, '_fetch_id_from_api') as mock_fetch:
        service = EtoroService()
        mock_fetch.return_value = 9999
        
        # 1. First Call (Cache Miss) - Ensure we don't hit disk cache
        service._id_cache.pop("XYZZY", None)
        id1 = await service._resolve_instrument_id("XYZZY")
        assert id1 == 9999
        assert mock_fetch.call_count == 1
        
        # 2. Second Call (Cache Hit)
        id2 = await service._resolve_instrument_id("XYZZY")
        assert id2 == 9999
        assert mock_fetch.call_count == 1  # Still 1 call

@pytest.mark.asyncio
async def test_resolve_instrument_id_no_match():
    """Verify logic when no instrument is found."""
    with patch.object(EtoroService, '_fetch_id_from_api', return_value=None):
        service = EtoroService()
        inst_id = await service._resolve_instrument_id("UNKNOWN_TICKER")
        assert inst_id is None

@pytest.mark.asyncio
async def test_execute_order_uses_id():
    """Verify execute_order calls resolve_id and uses it in payload."""
    # EtoroService now uses httpx in _fetch_portfolio_raw and execute_order logic likely uses similar async calls
    with patch('httpx.AsyncClient.post', new_callable=AsyncMock) as mock_post, \
         patch.object(EtoroService, '_resolve_instrument_id', return_value=555), \
         patch.object(EtoroService, '_fetch_portfolio_raw', return_value={'clientPortfolio': {'positions': []}}):
        
        service = EtoroService(user_id="test_user")
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = {"status": "success"}
        
        # Mock Risk Check pass
        service.risk_manager.check_constraints = MagicMock(return_value=True)
        service.get_history = AsyncMock(return_value=[])
        service.get_positions = AsyncMock(return_value=[])
        
        from src.domain.trading import Order, OrderAction
        order = Order(symbol="TSLA", action=OrderAction.BUY, quantity=10)
        
        await service.execute_order(order)
        
        # Verify that at least one call contains the InstrumentID
        execution_calls = [
            call for call in mock_post.call_args_list 
            if 'InstrumentID' in (call.kwargs.get('json', {}) or {})
        ]
        assert len(execution_calls) > 0, f"No execution call with InstrumentID found. Calls: {mock_post.call_args_list}"
        
        payload = execution_calls[0].kwargs['json']
        assert payload['InstrumentID'] == 555

@pytest.mark.asyncio
async def test_resolve_instrument_id_dynamic_tsla():
    """Verify TSLA now uses dynamic discovery (previously hardcoded)."""
    with patch.object(EtoroService, '_fetch_id_from_api', return_value=7):
        service = EtoroService(user_id="test_user")
        # Clear cache to force API call
        service._id_cache.pop("TSLA", None)
        
        inst_id = await service._resolve_instrument_id("TSLA")
        assert inst_id == 7


@pytest.mark.asyncio
async def test_resolve_instrument_id_full_response():
    """Verify resolution works with full API response (no fields param)."""
    # This test previously mocked requests.get, but it's cleaner to mock the internal API call
    # if the internal structure changed to httpx. 
    # Actually, _resolve_instrument_id calls _fetch_id_from_api.
    with patch.object(EtoroService, '_fetch_id_from_api', return_value=1832):
        service = EtoroService()
        service._id_cache.pop("AMD", None)
        
        inst_id = await service._resolve_instrument_id("AMD")
        # Should resolve to 1832
        assert inst_id == 1832


@pytest.mark.asyncio
async def test_execute_sell_includes_instrument_id():
    """Verify SELL close body includes required InstrumentId."""
    with patch('httpx.AsyncClient.post', new_callable=AsyncMock) as mock_post, \
         patch.object(EtoroService, '_resolve_instrument_id', return_value=5506), \
         patch.object(EtoroService, 'get_history', new_callable=AsyncMock, return_value=[]), \
         patch.object(EtoroService, '_fetch_portfolio_raw', new_callable=AsyncMock, return_value={'clientPortfolio': {'positions': []}}):
        
        service = EtoroService(user_id="test_user")
        service.risk_manager.check_constraints = MagicMock(return_value=True)
        
        # Mock a position matching our symbol
        from src.domain.trading import Position
        from datetime import datetime
        mock_pos = Position(
            symbol="CRWD", quantity=0.1, open_price=300.0,
            current_price=350.0, market_value=35.0,
            unrealized_pnl=5.0, open_date=datetime.now(),
            position_id="3024162344"
        )
        service.get_positions = AsyncMock(return_value=[mock_pos])
        
        from src.domain.trading import Order, OrderAction
        order = Order(symbol="CRWD", action=OrderAction.SELL, quantity=0)
        
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = {"status": "success"}
        
        await service.execute_order(order)
        
        # Verify close call includes InstrumentId
        close_calls = [
            call for call in mock_post.call_args_list
            if 'market-close-orders' in str(call)
        ]
        assert len(close_calls) > 0, f"No close call found. Calls: {mock_post.call_args_list}"
        close_payload = close_calls[0].kwargs.get('json', {})
        assert 'InstrumentId' in close_payload, f"InstrumentId missing from close body: {close_payload}"
        assert close_payload['InstrumentId'] == 5506


@pytest.mark.asyncio
async def test_execute_order_auth_failure_returns_clear_error():
    """Verify execute_order returns clear auth error instead of 'No active position'."""
    with patch.object(EtoroService, '_fetch_portfolio_raw', new_callable=AsyncMock,
                      return_value={'errorCode': 'Unauthorized', 'errorMessage': 'Unauthorized'}):
        
        service = EtoroService(user_id="test_user")
        
        from src.domain.trading import Order, OrderAction
        order = Order(symbol="TSLA", action=OrderAction.SELL, quantity=1.0)
        
        result = await service.execute_order(order)
        
        assert result['status'] == 'failed'
        assert 'Auth Failed' in result['reason']
        assert 'Unauthorized' in result['reason']
        # Must NOT show the misleading 'No active position' error
        assert 'No active position' not in result['reason']
