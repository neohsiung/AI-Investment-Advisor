import pytest
import asyncio
from unittest.mock import MagicMock, patch, AsyncMock
from src.services.etoro_service import EtoroService
from src.domain.trading import Order, OrderAction

@pytest.fixture
def service():
    with patch('src.services.etoro_service.os.path.exists', return_value=False):
        svc = EtoroService(base_url="http://mock-etoro", mode="demo")
        # Mock repos directly on service
        svc.transaction_repo = MagicMock()
        svc.settings_repo = MagicMock()
        svc.risk_manager.transaction_repo = svc.transaction_repo
        svc.risk_manager.settings_repo = svc.settings_repo
        
        # Default Settings
        def mock_get(uid, k, default=None):
            if k == "ai_trading_enabled": return "true"
            if k == "ai_max_daily_trades": return "10"
            return default
        svc.risk_manager.settings_repo.get.side_effect = mock_get
        
        # Aggressively mock all network-calling instance methods
        svc.get_history = AsyncMock(return_value=[])
        svc.get_positions = AsyncMock(return_value=[])
        svc.get_watchlists = AsyncMock(return_value=[])
        svc.get_account = AsyncMock(return_value=None)
        svc._fetch_portfolio_raw = AsyncMock(return_value={}) 
        svc._fetch_history_raw = AsyncMock(return_value=[])
        
        return svc

def test_check_constraints_ok(service):
    # Mock transaction count on RiskManager
    service.risk_manager._get_daily_trade_count = MagicMock(return_value=5)
    service.risk_manager._is_circuit_breaker_triggered = MagicMock(return_value=False)
    
    # Test directly on Risk Manager
    result = service.risk_manager.check_constraints("user1")
    assert result is True

def test_check_constraints_max_daily(service):
    # Mock on RiskManager
    service.risk_manager._get_daily_trade_count = MagicMock(return_value=10)
    result = service.risk_manager.check_constraints("user1")
    assert result is False

def test_circuit_breaker_trigger(service):
    # Mock on RiskManager
    service.risk_manager._get_daily_trade_count = MagicMock(return_value=5)
    service.risk_manager._is_circuit_breaker_triggered = MagicMock(return_value=True)
    
    result = service.risk_manager.check_constraints("user1")
    assert result is False
    
    # Check disable
    service.settings_repo.set.assert_called_with("user1", "ai_trading_enabled", "false")

@pytest.mark.asyncio
async def test_sync_history_logic(service):
    # We need to test the REAL logic of sync_history, so we un-mock it
    from src.services.etoro_service import EtoroService
    real_sync = EtoroService.sync_history
    
    # Mock dependencies of sync_history
    service.get_history = AsyncMock(return_value=[
        {
            "instrumentId": "1", 
            "openTimestamp": "2025-01-01T10:00:00", 
            "isBuy": True, 
            "units": 100, 
            "openRate": 150,
            "leverage": 1,
            "fees": 0
        }
    ])
    service.get_watchlists = AsyncMock(return_value={})
    service.transaction_repo.get_all_by_user.return_value = []
    service._id_to_symbol = {"1": "AAPL"}
    
    # Test Sync
    res = await real_sync(service, "user1")
    assert res['added'] == 1
    service.transaction_repo.add.assert_called_once()
    
@pytest.mark.asyncio
async def test_execute_order_wraps_risk_logic(service):
    # We need real logic for execute_order
    from src.services.etoro_service import EtoroService
    real_exec = EtoroService.execute_order
    
    # Mock dependencies
    service.risk_manager.check_constraints = MagicMock(return_value=False)
    service.get_history = AsyncMock(return_value=[])
    service.get_positions = AsyncMock(return_value=[])
    service._fetch_portfolio_raw = AsyncMock(return_value={}) 
    
    service.user_id = "test_user"
    order = Order(symbol="AAPL", action=OrderAction.BUY, quantity=100)
    
    res = await real_exec(service, order)
    assert res['status'] == 'failed'
    assert "Risk Manager" in res['reason']


class TestExecuteOrderDemoEndpointRouting:
    """
    2026-07-14 regression guard: execute_order() previously always hit the
    REAL eToro execution endpoint even when self.mode == "demo" — a user
    who believed they'd switched to safe paper trading was placing real
    orders. get_positions()/get_history() already routed to the /demo/
    endpoint namespace; execute_order must follow the same convention.
    """

    async def _run_buy(self, service, captured_urls):
        from src.services.etoro_service import EtoroService
        real_exec = EtoroService.execute_order
        service.risk_manager.check_constraints = MagicMock(return_value=True)
        service.get_history = AsyncMock(return_value=[])
        service.get_positions = AsyncMock(return_value=[])
        service._fetch_portfolio_raw = AsyncMock(return_value={})
        service._resolve_instrument_id = AsyncMock(return_value="1001")
        service.user_id = "test_user"

        class _Resp:
            def raise_for_status(self):
                pass

            def json(self):
                return {"orderForOpen": {"statusID": 2, "orderID": "abc"}}

        class _MockClient:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *a):
                return False

            async def post(self, url, **kwargs):
                captured_urls.append(url)
                return _Resp()

        with patch("httpx.AsyncClient", return_value=_MockClient()):
            order = Order(symbol="AAPL", action=OrderAction.BUY, quantity=100)
            await real_exec(service, order)

    @pytest.mark.asyncio
    async def test_demo_mode_hits_demo_execution_endpoint(self, service):
        assert service.mode == "demo"  # fixture default
        urls = []
        await self._run_buy(service, urls)
        assert len(urls) == 1
        assert "/trading/execution/demo/market-open-orders/by-amount" in urls[0]

    @pytest.mark.asyncio
    async def test_real_mode_hits_real_execution_endpoint(self, service):
        service.mode = "real"
        urls = []
        await self._run_buy(service, urls)
        assert len(urls) == 1
        assert "/trading/execution/market-open-orders/by-amount" in urls[0]
        assert "/demo/" not in urls[0]


@pytest.mark.asyncio
async def test_execute_order_buy_under_ten_dollars_fails(service):
    from src.services.etoro_service import EtoroService
    service.risk_manager.check_constraints = MagicMock(return_value=True)
    service.get_history = AsyncMock(return_value=[])
    service.get_positions = AsyncMock(return_value=[])
    service._resolve_instrument_id = AsyncMock(return_value="1001")
    service.user_id = "test_user"

    order = Order(symbol="AAPL", action=OrderAction.BUY, quantity=5.0, amount_usd=5.0)
    res = await EtoroService.execute_order(service, order)
    assert res["status"] == "failed"
    assert "below eToro minimum threshold" in res["reason"]


@pytest.mark.asyncio
async def test_execute_order_sell_precision_and_close_parsing(service):
    from src.services.etoro_service import EtoroService
    from src.domain.trading import Position
    service.risk_manager.check_constraints = MagicMock(return_value=True)
    service.get_history = AsyncMock(return_value=[])
    mock_pos = Position(
        symbol="AAPL", quantity=1.5, open_price=150.0, current_price=160.0,
        market_value=240.0, unrealized_pnl=15.0, position_id="pos_999"
    )
    service.get_positions = AsyncMock(return_value=[mock_pos])
    service._resolve_instrument_id = AsyncMock(return_value="1001")
    service.user_id = "test_user"

    captured_payloads = []

    class _MockClient:
        async def __aenter__(self):
            return self
        async def __aexit__(self, *a):
            return False
        async def post(self, url, json=None, **kwargs):
            captured_payloads.append(json)
            class _Resp:
                def raise_for_status(self):
                    pass
                def json(self):
                    return {"orderForClose": {"orderID": "close_123", "statusID": 2}}
            return _Resp()

    # Case A: Sell with quantity >= 0.01 sets UnitsToDeduct
    with patch("httpx.AsyncClient", return_value=_MockClient()):
        order = Order(symbol="AAPL", action=OrderAction.SELL, quantity=0.555)
        res = await EtoroService.execute_order(service, order)
        assert res["status"] == "success"
        assert res["execution_status"] == "executed"
        assert res["order_id"] == "close_123"
        assert captured_payloads[0]["UnitsToDeduct"] == 0.56

    # Case B: Sell with quantity < 0.01 omits UnitsToDeduct (full close)
    captured_payloads.clear()
    with patch("httpx.AsyncClient", return_value=_MockClient()):
        order_tiny = Order(symbol="AAPL", action=OrderAction.SELL, quantity=0.004)
        res_tiny = await EtoroService.execute_order(service, order_tiny)
        assert res_tiny["status"] == "success"
        assert "UnitsToDeduct" not in captured_payloads[0]


@pytest.mark.asyncio
async def test_execute_order_buy_with_leverage_and_trailing_stop(service):
    from src.services.etoro_service import EtoroService
    service.risk_manager.check_constraints = MagicMock(return_value=True)
    service.get_history = AsyncMock(return_value=[])
    service.get_positions = AsyncMock(return_value=[])
    service._resolve_instrument_id = AsyncMock(return_value="1001")
    service.user_id = "test_user"

    captured_payloads = []

    class _MockClient:
        async def __aenter__(self):
            return self
        async def __aexit__(self, *a):
            return False
        async def post(self, url, json=None, **kwargs):
            captured_payloads.append(json)
            class _Resp:
                def raise_for_status(self):
                    pass
                def json(self):
                    return {"orderForOpen": {"orderID": "open_777", "statusID": 2}}
            return _Resp()

    with patch("httpx.AsyncClient", return_value=_MockClient()):
        order = Order(
            symbol="NVDA",
            action=OrderAction.BUY,
            quantity=50.0,
            amount_usd=50.0,
            leverage=2,
            stop_loss_rate=110.5,
            take_profit_rate=140.0,
            is_trailing_stop_loss=True,
        )
        res = await EtoroService.execute_order(service, order)
        assert res["status"] == "success"
        assert res["order_id"] == "open_777"
        payload = captured_payloads[0]
        assert payload["Leverage"] == 2
        assert payload["StopLossRate"] == 110.5
        assert payload["TakeProfitRate"] == 140.0
        assert payload["IsTrailingStopLoss"] is True


