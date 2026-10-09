import unittest
from unittest.mock import MagicMock, patch, AsyncMock
from datetime import datetime, timedelta, timezone
from src.services.outcome_reflection_service import OutcomeReflectionService, DEFAULT_BENCHMARK


class TestOutcomeReflectionService(unittest.TestCase):
    def setUp(self):
        self.user_id = "test_user_123"
        self.mock_engine = MagicMock()
        with patch("src.services.outcome_reflection_service.get_db_engine", return_value=self.mock_engine), \
             patch("src.services.outcome_reflection_service.resolve_user_id", return_value=self.user_id):
            self.service = OutcomeReflectionService(user_id=self.user_id)

    def test_fetch_price_from_market_data_service_latest(self):
        mock_mds = MagicMock()
        mock_mds.get_ohlcv.return_value = {
            "date": ["2026-09-28", "2026-09-29", "2026-09-30"],
            "close": [330.0, 335.0, 340.0],
        }
        self.service._mds = mock_mds

        price = self.service._fetch_price("AAPL")
        self.assertEqual(price, 340.0)
        mock_mds.get_ohlcv.assert_called_once_with("AAPL", days=5)

    def test_fetch_price_from_market_data_service_as_of(self):
        mock_mds = MagicMock()
        mock_mds.get_ohlcv.return_value = {
            "date": ["2026-09-25", "2026-09-28", "2026-09-29", "2026-09-30", "2026-10-01"],
            "close": [325.0, 330.0, 335.0, 338.0, 342.0],
        }
        self.service._mds = mock_mds

        as_of_dt = datetime(2026, 9, 30, 15, 0, tzinfo=timezone.utc)
        price = self.service._fetch_price("AAPL", as_of=as_of_dt)
        self.assertEqual(price, 338.0)

    def test_fetch_price_fallback_to_quote_batch(self):
        mock_mds = MagicMock()
        mock_mds.get_ohlcv.return_value = {}  # Empty OHLCV

        mock_provider = MagicMock()
        mock_provider.fetch_current_prices.return_value = {"AAPL": 345.5}
        mock_mds._chain.return_value = [mock_provider]
        mock_mds._is_provider_enabled.return_value = True

        self.service._mds = mock_mds

        price = self.service._fetch_price("AAPL")
        self.assertEqual(price, 345.5)

    def test_fetch_price_fallback_to_yfinance(self):
        mock_mds = MagicMock()
        mock_mds.get_ohlcv.return_value = {}
        mock_mds._chain.return_value = []
        self.service._mds = mock_mds

        import pandas as pd
        mock_hist = pd.DataFrame({"Close": [333.33]}, index=[pd.Timestamp("2026-09-30")])

        with patch("yfinance.Ticker") as mock_yf:
            mock_yf.return_value.history.return_value = mock_hist
            price = self.service._fetch_price("AAPL")
            self.assertEqual(price, 333.33)

    def test_fetch_benchmark_window_from_market_data_service(self):
        mock_mds = MagicMock()
        mock_mds.get_ohlcv.return_value = {
            "date": ["2026-09-25", "2026-09-28", "2026-09-29", "2026-09-30", "2026-10-01"],
            "close": [770.0, 768.0, 765.0, 760.0, 775.0],
        }
        self.service._mds = mock_mds

        start_dt = datetime(2026, 9, 25, 10, 0, tzinfo=timezone.utc)
        end_dt = datetime(2026, 9, 30, 16, 0, tzinfo=timezone.utc)

        then_price, now_price = self.service._fetch_benchmark_window(start_dt, end_dt)
        self.assertEqual(then_price, 770.0)
        self.assertEqual(now_price, 760.0)
        mock_mds.get_ohlcv.assert_called_once()
        self.assertEqual(mock_mds.get_ohlcv.call_args[0][0], DEFAULT_BENCHMARK)

    def test_fetch_benchmark_window_fallback_to_yfinance(self):
        mock_mds = MagicMock()
        mock_mds.get_ohlcv.return_value = {}
        self.service._mds = mock_mds

        import pandas as pd
        mock_hist = pd.DataFrame({"Close": [750.0, 760.0]}, index=[pd.Timestamp("2026-09-25"), pd.Timestamp("2026-09-30")])

        with patch("yfinance.Ticker") as mock_yf:
            mock_yf.return_value.history.return_value = mock_hist
            start_dt = datetime(2026, 9, 25, tzinfo=timezone.utc)
            end_dt = datetime(2026, 9, 30, tzinfo=timezone.utc)
            then_p, now_p = self.service._fetch_benchmark_window(start_dt, end_dt)
            self.assertEqual(then_p, 750.0)
            self.assertEqual(now_p, 760.0)

    def test_resolve_one_not_due_yet(self):
        row = {
            "id": "dec-1",
            "ticker": "AAPL",
            "signal": "BUY",
            "price_at_decision": 150.0,
            "decided_at": datetime.now(timezone.utc) - timedelta(days=2),
            "horizon_days": 5,
        }
        resolved = self.service._resolve_one(row)
        self.assertFalse(resolved)

    def test_resolve_one_success_and_updates_db(self):
        row = {
            "id": "dec-100",
            "ticker": "AAPL",
            "signal": "BUY",
            "agent_name": "Valuation",
            "price_at_decision": 300.0,
            "decided_at": datetime(2026, 9, 25, 10, 0, tzinfo=timezone.utc),
            "horizon_days": 5,
        }

        mock_conn = MagicMock()
        self.service.engine.begin.return_value.__enter__.return_value = mock_conn

        with patch.object(self.service, "_fetch_price", return_value=330.0) as mock_p, \
             patch.object(self.service, "_fetch_benchmark_window", return_value=(700.0, 735.0)) as mock_b, \
             patch.object(self.service, "_generate_lesson", return_value="Great AAPL alpha.") as mock_l, \
             patch("src.services.rule_lifecycle_service.RuleLifecycleService") as MockRuleLifecycle:

            mock_rule_svc = MockRuleLifecycle.return_value
            resolved = self.service._resolve_one(row)

            self.assertTrue(resolved)
            mock_p.assert_called_once_with("AAPL", as_of=row["decided_at"] + timedelta(days=5))
            mock_b.assert_called_once()
            mock_l.assert_called_once()

            # Price moved 300 -> 330 (+10.0%)
            # SPY moved 700 -> 735 (+5.0%)
            # Alpha = +5.0%
            mock_rule_svc.backfill_score.assert_called_once()
            call_args = mock_rule_svc.backfill_score.call_args[0]
            self.assertEqual(call_args[0], "dec-100")
            self.assertAlmostEqual(call_args[1], 5.0, places=2)

            # DB Update check
            mock_conn.execute.assert_called_once()
            update_params = mock_conn.execute.call_args[0][1]
            self.assertEqual(update_params["id"], "dec-100")
            self.assertAlmostEqual(update_params["realized"], 10.0, places=2)
            self.assertAlmostEqual(update_params["benchmark"], 5.0, places=2)
            self.assertAlmostEqual(update_params["alpha"], 5.0, places=2)
            self.assertEqual(update_params["lesson"], "Great AAPL alpha.")

    def test_resolve_pending_batch(self):
        rows = [
            {"id": "d1", "ticker": "AAPL", "decided_at": datetime.now(timezone.utc) - timedelta(days=10), "horizon_days": 5, "price_at_decision": 100},
            {"id": "d2", "ticker": "MSFT", "decided_at": datetime.now(timezone.utc) - timedelta(days=1), "horizon_days": 5, "price_at_decision": 200},
        ]
        with patch.object(self.service, "_fetch_due_pending", return_value=rows), \
             patch.object(self.service, "_resolve_one", side_effect=[True, False]):

            summary = self.service.resolve_pending(max_batch=10)
            self.assertEqual(summary["checked"], 2)
            self.assertEqual(summary["resolved"], 1)
            self.assertEqual(summary["skipped"], 1)
            self.assertEqual(summary["failed"], 0)

    def test_clean_lesson_normal_text(self):
        normal = "AAPL gained +1.50% alpha over SPY, validating entry timing."
        cleaned = self.service._clean_lesson(normal, "AAPL", "BUY", 1.50)
        self.assertEqual(cleaned, normal)

    def test_clean_lesson_extracts_from_scratchpad(self):
        scratchpad = """Here's a thinking process:
1. Analyze User Request:
   - Input: AAPL BUY
Draft 1:
"The BUY call on AAPL delivered +2.50% alpha vs SPY, showing strong relative strength."
Check: looks good.
"""
        cleaned = self.service._clean_lesson(scratchpad, "AAPL", "BUY", 2.50)
        self.assertEqual(cleaned, "The BUY call on AAPL delivered +2.50% alpha vs SPY, showing strong relative strength.")

    def test_clean_lesson_fallback_when_no_quote(self):
        corrupted = "Here's a thinking process: 1. Analyze User Request without quotes..."
        cleaned = self.service._clean_lesson(corrupted, "AAPL", "BUY", 1.25)
        self.assertIn("outperformed the SPY benchmark by 1.25pp", cleaned)

