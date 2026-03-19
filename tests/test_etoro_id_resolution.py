
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
        
        # Verify that at least one call contains the InstrumentId
        execution_calls = [
            call for call in mock_post.call_args_list 
            if 'InstrumentId' in (call.kwargs.get('json', {}) or {})
        ]
        assert len(execution_calls) > 0, f"No execution call with InstrumentId found. Calls: {mock_post.call_args_list}"
        
        payload = execution_calls[0].kwargs['json']
        assert payload['InstrumentId'] == 555

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
