import pytest
import asyncio
from unittest.mock import MagicMock, AsyncMock, patch
from tests.fixtures.sentinel_fixtures import _create_sentinel

class TestVIXAnomaly:
    def test_calm_market_no_trigger(self, mock_services, run_async):
        """Standard VIX (20.0) — no trigger."""
        print("DEBUG: test_calm_market_no_trigger start")
        sentinel = _create_sentinel(mock_services)

        mock_services["market"].get_ohlcv.return_value = {"close": [15.0] * 60}
        mock_services["transaction"].get_user_tickers.return_value = []
        # Suppress cash alert in calm market test
        mock_services["settings"].get_setting.side_effect = lambda key, default=None, user_id=None: 0.0 if key == "target_cash_ratio" else default

        async def _test():
            # Patch _get_all_user_ids and _check_active_sources to avoid DB
            with patch.object(sentinel, '_get_all_user_ids', return_value=[]), \
                 patch.object(sentinel, '_check_active_sources', return_value=[]), \
                 patch('httpx.AsyncClient.post') as mock_post:
                await sentinel.process_tick()
                mock_post.assert_not_called()
            mock_services["council"].start_session.assert_not_called()

        run_async(_test())

    def test_vix_spike_triggers_council(self, mock_services, run_async):
        """VIX spikes from 15 to 25 — adaptive trigger fires."""
        sentinel = _create_sentinel(mock_services)
        history = [15.0] * 59 + [25.0]
        mock_services["market"].get_ohlcv.return_value = {"close": history}
        mock_services["market"].get_current_prices.return_value = {}
        mock_services["market"].get_macro_data.return_value = {}
        mock_services["transaction"].get_user_tickers.return_value = []

        async def _test():
            with patch.object(sentinel, '_get_all_user_ids', return_value=[]):
                await sentinel.process_tick()
                await sentinel._flush_buffer(force=True)
            mock_services["council"].start_session.assert_called_once()
            args = mock_services["council"].start_session.call_args[0]
            assert "VIX Spike" in args[0]

        run_async(_test())

    def test_vix_static_fallback(self, mock_services, run_async):
        """Short history — uses static threshold."""
        sentinel = _create_sentinel(mock_services)
        # 3.9 - Ensure thresholds are mockable
        sentinel.thresholds = {"vix_high": 20.0}
        
        mock_services["market"].get_ohlcv.return_value = {"close": [22.0]}
        
        async def _test():
            # Test the dimension logic directly to ensure it works
            triggers = sentinel._check_vix_anomaly()
            assert len(triggers) == 1
            assert "vix_high_static" in triggers[0]["id"]
            
            # Now test the escalation via _escalate
            sentinel._dispatch_notifications_direct = AsyncMock()
            await sentinel._escalate(triggers)
            await sentinel._flush_buffer(force=True) # Force flush for testing
            mock_services["council"].start_session.assert_called_once()
            assert sentinel._dispatch_notifications_direct.called

        run_async(_test())


# ──────────────────────────────────────────
# Dimension 2: Position Price Moves
# ──────────────────────────────────────────

class TestPositionMoves:
    def test_position_drop_trigger(self, mock_services, run_async):
        """Stock drops > 5% intraday — triggers alert."""
        # Use the global mock instance from the fixture
        repo_instance = mock_services["repo_instance"]
        repo_instance.get_all_thresholds.return_value = {
            "position_drop_pct": -5.0,
            "position_spike_pct": 8.0,
        }

        async def _test():
            # Create sentinel - it will use the mocked Repo class from fixture
            sentinel = _create_sentinel(mock_services)
            
            # Setup market data for the drop
            mock_services["market"].get_ohlcv_batch.return_value = {
                "AAPL": {"close": [100.0, 89.0]} # -11%
            }
            mock_services["market"].get_current_prices.return_value = {"AAPL": 89.0}
            mock_services["transaction"].get_user_tickers.return_value = ["AAPL"]
            
            # Mock internal user methods
            sentinel.user_id = "user@test.com"
            with patch.object(sentinel, '_get_all_user_ids', return_value=["user@test.com"]):
                    await sentinel.process_tick()
                    await sentinel._flush_buffer(force=True)

            # Verification
            mock_services["council"].start_session.assert_called_once()
            args = mock_services["council"].start_session.call_args[0]
            assert "AAPL" in args[0]

        run_async(_test())

    def test_position_spike_trigger(self, mock_services, run_async):
        """Stock spikes > 8% intraday — triggers alert."""
        # Use the global mock instance
        repo_instance = mock_services["repo_instance"]
        repo_instance.get_all_thresholds.return_value = {
            "position_drop_pct": -5.0,
            "position_spike_pct": 8.0,
        }
    
        async def _test():
            sentinel = _create_sentinel(mock_services)
            
            # Market data for spike
            mock_services["market"].get_ohlcv_batch.return_value = {
                "TSLA": {"close": [100.0, 110.0]} # +10%
            }
            mock_services["market"].get_current_prices.return_value = {"TSLA": 110.0}
            mock_services["transaction"].get_user_tickers.return_value = ["TSLA"]
            
            with patch.object(sentinel, '_get_all_user_ids', return_value=["user@test.com"]):
                await sentinel.process_tick()
                await sentinel._flush_buffer(force=True)

            # Verification
            mock_services["council"].start_session.assert_called_once()
            args = mock_services["council"].start_session.call_args[0]
            assert "TSLA" in args[0]

        run_async(_test())

    def test_position_bubble_trigger(self, mock_services, run_async):
        """Stock rises > 8% — triggers bubble warning."""
        sentinel = _create_sentinel(mock_services)
        mock_services["market"].get_ohlcv_batch.return_value = {
            "TSLA": {"close": [100.0, 110.0]}
        }
        mock_services["market"].get_current_prices.return_value = {"TSLA": 110.0}
        mock_services["market"].get_macro_data.return_value = {}
        mock_services["transaction"].get_user_tickers.return_value = ["TSLA"]

        async def _test():
            with patch.object(sentinel, '_get_all_user_ids', return_value=["user@test.com"]):
                await sentinel.process_tick()
                await sentinel._flush_buffer(force=True)
            mock_services["council"].start_session.assert_called_once()
            args = mock_services["council"].start_session.call_args[0]
            assert "TSLA" in args[0]
            assert "漲" in args[0]

        run_async(_test())

    def test_no_trigger_small_move(self, mock_services, run_async):
        """Stock moves < 5% — no trigger."""
        sentinel = _create_sentinel(mock_services)
        mock_services["market"].get_ohlcv_batch.return_value = {
            "MSFT": {"close": [100.0, 98.0]}
        }
        mock_services["market"].get_current_prices.return_value = {"MSFT": 98.0}
        mock_services["transaction"].get_user_tickers.return_value = ["MSFT"]
        mock_services["transaction"].get_user_tickers.return_value = ["MSFT"]

        async def _test():
            with patch.object(sentinel, '_get_all_user_ids', return_value=["user@test.com"]), \
                 patch.object(sentinel, '_check_active_sources', return_value=[]):
                await sentinel.process_tick()
            mock_services["council"].start_session.assert_not_called()

        run_async(_test())



class TestMacroShifts:
    def test_fed_rate_up_triggers(self, mock_services, run_async):
        """Fed funds rate trending up — triggers alert."""
        sentinel = _create_sentinel(mock_services)
        mock_services["market"].get_macro_data.return_value = {
            "economics": {
                "FedFunds": {"value": 5.5, "trend": "Up", "date": "2026-02-14"},
                "10Y2Y_Spread": {"value": 0.5},
            }
        }

        async def _test():
            triggers = await sentinel._check_macro_shifts()
            assert len(triggers) == 1
            assert "聯邦利率上升" in triggers[0]["text"]

        run_async(_test())

    def test_yield_inversion_triggers(self, mock_services, run_async):
        """Yield curve inverted — triggers alert."""
        sentinel = _create_sentinel(mock_services)
        mock_services["market"].get_macro_data.return_value = {
            "economics": {
                "FedFunds": {"value": 5.0, "trend": "Down", "date": "2026-02-14"},
                "10Y2Y_Spread": {"value": -0.3},
            }
        }

        async def _test():
            triggers = await sentinel._check_macro_shifts()
            assert len(triggers) == 1
            assert "殖利率曲線倒掛" in triggers[0]["text"]

        run_async(_test())

    def test_normal_macro_no_trigger(self, mock_services, run_async):
        """Normal macro conditions — no trigger."""
        sentinel = _create_sentinel(mock_services)
        mock_services["market"].get_macro_data.return_value = {
            "economics": {
                "FedFunds": {"value": 5.0, "trend": "Down", "date": "2026-02-14"},
                "10Y2Y_Spread": {"value": 0.5},
            }
        }

        async def _test():
            triggers = await sentinel._check_macro_shifts()
            assert len(triggers) == 0

        run_async(_test())




