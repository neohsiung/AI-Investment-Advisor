"""
Unit Tests for Staggered Dip Buying Order Stalking & MOC Conversion (Phase 48)
"""

import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import pandas as pd
import numpy as np

from src.services.staggered_dip_buying_service import StaggeredDipBuyingService


@pytest.fixture
def mock_redis():
    r = MagicMock()
    stored = {}

    async def async_get(key):
        return stored.get(key)

    async def async_setex(key, ttl, val):
        stored[key] = val
        return True

    r.get = AsyncMock(side_effect=async_get)
    r.setex = AsyncMock(side_effect=async_setex)
    r._stored = stored
    return r


@pytest.mark.asyncio
async def test_stalk_and_reprice_pending_orders(mock_redis):
    svc = StaggeredDipBuyingService(user_id="test_user")

    # Mock orders in Redis: 1 Tier 1 PENDING, 1 Tier 3 PENDING
    orders = [
        {
            "ticker": "NVDA",
            "tier_number": 1,
            "tier_name": "Tier 1 (輕度回踩)",
            "limit_price": 100.0,
            "amount_usd": 30.0,
            "discount_pct": 0.02,
            "status": "PENDING",
        },
        {
            "ticker": "NVDA",
            "tier_number": 3,
            "tier_name": "Tier 3 (深度折價)",
            "limit_price": 90.0,
            "amount_usd": 20.0,
            "discount_pct": 0.12,
            "status": "PENDING",
        },
    ]

    import pytz
    from datetime import datetime
    now_ny = datetime.now(pytz.timezone("US/Eastern"))
    date_str = now_ny.strftime("%Y-%m-%d")
    r_key = f"{svc.REDIS_KEY_PREFIX}:test_user:{date_str}"
    mock_redis._stored[r_key] = json.dumps(orders)

    # Mock market data service: stock is trading at 105 (up from open 102)
    mkt_mock = MagicMock()
    mkt_mock.get_quote.return_value = {"last": 105.0, "close": 105.0}
    dates = pd.date_range("2026-10-01", periods=5, freq="D")
    df = pd.DataFrame({"Open": [100, 101, 101.5, 102, 102.5], "Close": [101, 101.8, 102, 103, 105]}, index=dates)
    mkt_mock.get_history_df.return_value = df

    with patch("src.infrastructure.cache.redis_client.get_redis", AsyncMock(return_value=mock_redis)), \
         patch.object(svc, "_get_market_data_service", AsyncMock(return_value=mkt_mock)), \
         patch.object(svc, "dispatch_staggered_stalk_alert", AsyncMock(return_value=True)):

        res = await svc.stalk_and_reprice_pending_orders()
        assert res["status"] == "success"
        assert res["repriced_count"] == 1

        repriced = res["orders"][0]
        assert repriced["ticker"] == "NVDA"
        assert repriced["limit_price"] > 100.0  # Repriced upwards
        assert repriced["is_stalked"] is True

        # Check that Redis was updated
        saved_orders = json.loads(mock_redis._stored[r_key])
        assert saved_orders[0]["limit_price"] > 100.0
        assert saved_orders[1]["limit_price"] == 90.0  # Tier 3 was untouched


@pytest.mark.asyncio
async def test_convert_unfilled_dip_orders_to_moc(mock_redis):
    svc = StaggeredDipBuyingService(user_id="test_user")

    orders = [
        {
            "ticker": "TSM",
            "tier_number": 1,
            "tier_name": "Tier 1 (輕度回踩)",
            "limit_price": 180.0,
            "amount_usd": 40.0,
            "discount_pct": 0.015,
            "status": "PENDING",
        }
    ]

    import pytz
    from datetime import datetime
    now_ny = datetime.now(pytz.timezone("US/Eastern"))
    date_str = now_ny.strftime("%Y-%m-%d")
    r_key = f"{svc.REDIS_KEY_PREFIX}:test_user:{date_str}"
    mock_redis._stored[r_key] = json.dumps(orders)

    mkt_mock = MagicMock()
    mkt_mock.get_quote.return_value = {"last": 182.5, "close": 182.5}

    with patch("src.infrastructure.cache.redis_client.get_redis", AsyncMock(return_value=mock_redis)), \
         patch.object(svc, "_get_market_data_service", AsyncMock(return_value=mkt_mock)), \
         patch.object(svc, "_get_broker", AsyncMock(return_value=None)), \
         patch.object(svc, "_onboard_filled_position", AsyncMock(return_value=173.0)), \
         patch.object(svc, "dispatch_staggered_moc_alert", AsyncMock(return_value=True)):

        res = await svc.convert_unfilled_dip_orders_to_moc()
        assert res["status"] == "success"
        assert res["converted_count"] == 1

        conv = res["orders"][0]
        assert conv["status"] == "FILLED"
        assert conv["fill_price"] == 182.5
        assert conv["fill_mechanism"] == "MOC_CONVERSION"
        assert conv["initial_stop_price"] == 173.0
