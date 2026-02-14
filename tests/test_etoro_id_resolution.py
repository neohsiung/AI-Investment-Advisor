
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
        # First call returns list
        mock_get.return_value.json.return_value = [mock_etoro_response]
        
        # 1. First Call (Cache Miss)
        id1 = service._resolve_instrument_id("AAPL")
        assert id1 == 1001
        assert mock_get.call_count == 1
        
        # 2. Second Call (Cache Hit)
        id2 = service._resolve_instrument_id("AAPL")
        assert id2 == 1001
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
        
        args, kwargs = mock_post.call_args
        payload = kwargs['json']
        
        assert payload['InstrumentID'] == 555
        assert payload.get('Instrument') is None 
        # Checking implementation: I replaced 'Instrument' with 'InstrumentID' in payload construction?
        # Let's check code replaced in snippet 2038.
        # Yes: "InstrumentID": instrument_id
        
        assert 'InstrumentID' in payload
