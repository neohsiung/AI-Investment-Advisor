import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from src.services.sentinel_service import SentinelService

@pytest.fixture
def mock_deps():
    with patch('src.services.sentinel_service.MarketDataService') as mock_market_cls, \
         patch('src.services.sentinel_service.CouncilService') as mock_council_cls, \
         patch('src.services.sentinel_service.LineBotAdapter') as mock_line_cls:
        
        mock_market = mock_market_cls.return_value
        mock_council = mock_council_cls.return_value
        mock_line = mock_line_cls.return_value
        
        # Async mock for Council
        mock_council.start_session = AsyncMock()
        
        yield {
            'market': mock_market,
            'council': mock_council,
            'line': mock_line
        }

import asyncio

@pytest.fixture
def run_async():
    def _run(coro):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(coro)
        finally:
            loop.close()
    return _run

def test_sentinel_normal_market(mock_deps, run_async):
    """Test Sentinel behavior when market is calm (VIX low)."""
    async def _test():
        service = SentinelService()
        
        # Mock VIX history (Calm: ~15)
        mock_deps['market'].get_ohlcv.return_value = {
            "close": [15.0] * 60
        }
        
        await service.process_tick()
        
        # Verify no Council call
        mock_deps['council'].start_session.assert_not_called()
        # Verify no Alert
        mock_deps['line'].send_flex_alert.assert_not_called()
        
    run_async(_test())

def test_sentinel_vix_spike_adaptive(mock_deps, run_async):
    """Test Sentinel triggers Council on VIX Spike (Adaptive Logic)."""
    async def _test():
        service = SentinelService()
        
        # Mock VIX history:
        # 59 days of 15.0, then suddenly 25.0
        history = [15.0] * 59 + [25.0]
        mock_deps['market'].get_ohlcv.return_value = {
            "close": history
        }
        
        # Mock Council Decision
        mock_deps['council'].start_session.return_value = {
            "consensus": "We should reduce exposure due to volatility spike."
        }
        
        await service.process_tick()
        
        # Verify Council summoned
        mock_deps['council'].start_session.assert_called_once()
        args, _ = mock_deps['council'].start_session.call_args
        assert "SENTINEL ALERT" in args[0]
        assert "Adaptive Volatility Alert" in args[0]
        
        # Verify LINE Alert sent
        mock_deps['line'].send_flex_alert.assert_called_once()
        alert_args = mock_deps['line'].send_flex_alert.call_args
        assert "reduce exposure" in alert_args[1]['content'] # content arg

    run_async(_test())

def test_sentinel_vix_static_fallback(mock_deps, run_async):
    """Test static threshold trigger when history is insufficient."""
    async def _test():
        service = SentinelService()
        service.thresholds["vix_high"] = 20.0
        
        # Short history (e.g. 1 day of high VIX)
        mock_deps['market'].get_ohlcv.return_value = {
            "close": [22.0]
        }
        
        mock_deps['council'].start_session.return_value = {"consensus": "Hold"}
        
        await service.process_tick()
        
        # Should trigger static rule
        mock_deps['council'].start_session.assert_called()
        args, _ = mock_deps['council'].start_session.call_args
        assert "Static Volatility Alert" in args[0]

    run_async(_test())

def test_sentinel_error_handling(mock_deps, caplog, run_async):
    """Test error handling prevents crash."""
    async def _test():
        service = SentinelService()
        
        # Market service raises error
        mock_deps['market'].get_ohlcv.side_effect = Exception("API Error")
        
        await service.process_tick()
        
        # Should log error but not crash
        assert "Sentinel Tick Error" in caplog.text

    run_async(_test())
