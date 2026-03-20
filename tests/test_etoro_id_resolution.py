
import pytest
from unittest.mock import MagicMock, patch
from src.services.etoro_service import EtoroService

@pytest.fixture
def mock_etoro_response():
    return {
        "InstrumentID": 1001,
        "SymbolFull": "AAPL",
        "InstrumentDisplayName": "Apple Inc."
    }

def test_resolve_instrument_id_cache(mock_etoro_response):
    """Verify caching logic avoids redundant API calls."""
    with patch('src.services.etoro_service.requests.get') as mock_get:
        service = EtoroService()
        mock_get.return_value.status_code = 200
        mock_get.return_value.json.return_value = [{"instrumentId": 9999, "symbolName": "XYZZY"}]
        # 1. First Call (Cache Miss) - Ensure we don't hit disk cache
        service._id_cache.pop("XYZZY", None)
        id1 = service._resolve_instrument_id("XYZZY")
        assert id1 == 9999
        assert mock_get.call_count == 1
        
        # 2. Second Call (Cache Hit)
        id2 = service._resolve_instrument_id("XYZZY")
        assert id2 == 9999
        assert mock_get.call_count == 1  # Still 1 call

def test_resolve_instrument_id_no_match():
    """Verify logic when no instrument is found."""
    with patch('src.services.etoro_service.requests.get') as mock_get:
        service = EtoroService()
        mock_get.return_value.status_code = 200
        mock_get.return_value.json.return_value = [] # Empty list
        
        inst_id = service._resolve_instrument_id("UNKNOWN_TICKER")
        assert inst_id is None

def test_execute_order_uses_id():
    """Verify execute_order calls resolve_id and uses it in payload."""
    with patch('src.services.etoro_service.requests.post') as mock_post, \
         patch.object(EtoroService, '_resolve_instrument_id', return_value=555):
        
        service = EtoroService()
        # Mock Risk Check pass
        service.risk_manager.check_constraints = MagicMock(return_value=True)
        service.get_history = MagicMock(return_value=[])
        service.get_positions = MagicMock(return_value=[])
        
        from src.domain.trading import Order, OrderAction
        order = Order(symbol="TSLA", action=OrderAction.BUY, quantity=10)
        
        service.execute_order(order)
        
        # Verify that at least one call contains the InstrumentID
        execution_calls = [
            call for call in mock_post.call_args_list 
            if 'InstrumentID' in (call.kwargs.get('json', {}) or {})
        ]
        assert len(execution_calls) > 0, f"No execution call with InstrumentID found. Calls: {mock_post.call_args_list}"
        
        payload = execution_calls[0].kwargs['json']
        assert payload['InstrumentID'] == 555

def test_resolve_instrument_id_dynamic_tsla():
    """Verify TSLA now uses dynamic discovery (previously hardcoded)."""
    with patch('src.services.etoro_service.requests.get') as mock_get:
        service = EtoroService()
        # Clear cache to force API call
        service._id_cache.pop("TSLA", None)
        mock_get.return_value.status_code = 200
        mock_get.return_value.json.return_value = [{"instrumentId": 7, "internalSymbolFull": "TSLA"}]
        
        inst_id = service._resolve_instrument_id("TSLA")
        assert inst_id == 7
        assert mock_get.call_count == 1


def test_resolve_instrument_id_full_response():
    """Verify resolution works with full API response (no fields param)."""
    with patch('src.services.etoro_service.requests.get') as mock_get:
        service = EtoroService()
        service._id_cache.pop("AMD", None)
        # Simulate full search response with isCurrentlyTradable
        mock_get.return_value.status_code = 200
        mock_get.return_value.json.return_value = {
            "page": 1, "pageSize": 10, "totalItems": 3,
            "items": [
                {"instrumentId": 1832, "internalSymbolFull": "AMD", "isCurrentlyTradable": True, "isActiveInPlatform": True},
                {"instrumentId": 14262, "internalSymbolFull": "AMD.EUR", "isCurrentlyTradable": False, "isActiveInPlatform": False},
                {"instrumentId": 2493, "internalSymbolFull": "AMD.RTH", "isCurrentlyTradable": False, "isActiveInPlatform": False},
            ]
        }
        
        inst_id = service._resolve_instrument_id("AMD")
        # Should resolve to 1832 (the tradable one)
        assert inst_id == 1832


def test_execute_sell_includes_instrument_id():
    """Verify SELL close body includes required InstrumentId."""
    with patch('src.services.etoro_service.requests.post') as mock_post, \
         patch.object(EtoroService, '_resolve_instrument_id', return_value=5506), \
         patch.object(EtoroService, 'get_history', return_value=[]):
        
        service = EtoroService()
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
        service.get_positions = MagicMock(return_value=[mock_pos])
        
        from src.domain.trading import Order, OrderAction
        order = Order(symbol="CRWD", action=OrderAction.SELL, quantity=0)
        
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = {"status": "success"}
        mock_post.return_value.raise_for_status = MagicMock()
        
        service.execute_order(order)
        
        # Verify close call includes InstrumentId
        close_calls = [
            call for call in mock_post.call_args_list
            if 'market-close-orders' in str(call)
        ]
        assert len(close_calls) > 0, f"No close call found. Calls: {mock_post.call_args_list}"
        close_payload = close_calls[0].kwargs.get('json', {})
        assert 'InstrumentId' in close_payload, f"InstrumentId missing from close body: {close_payload}"
        assert close_payload['InstrumentId'] == 5506
