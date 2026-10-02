"""
Unit tests for EtoroService._backfill_from_positions idempotency and anti-duplication.
測試 EtoroService 持倉回補機制的冪等性與防重複寫入保護。
"""

import pytest
from unittest.mock import AsyncMock, MagicMock
from datetime import datetime
from src.services.etoro_service import EtoroService
from src.domain.trading import Position


class DummyTx:
    def __init__(self, ticker, action, trade_date, quantity, price, source_file=None, raw_data=None):
        self.ticker = ticker
        self.action = action
        self.trade_date = trade_date
        self.quantity = quantity
        self.price = price
        self.source_file = source_file
        self.raw_data = raw_data


@pytest.mark.asyncio
async def test_backfill_from_positions_idempotency():
    # Setup mock transaction repo
    mock_repo = MagicMock()
    stored_txs = []

    def fake_get_all_by_user(user_id, account_id=None):
        return list(stored_txs)

    def fake_add(user_id, ticker, date, action, quantity, price, fees, leverage=1.0, source_file=None, entry_category="trade", raw_data=None):
        tx = DummyTx(
            ticker=ticker,
            action=action,
            trade_date=date,
            quantity=quantity,
            price=price,
            source_file=source_file,
            raw_data=raw_data,
        )
        tx.entry_category = entry_category
        stored_txs.append(tx)
        return f"tx_{len(stored_txs)}"

    mock_repo.get_all_by_user.side_effect = fake_get_all_by_user
    mock_repo.add.side_effect = fake_add

    # Initialize EtoroService with mocked repo
    service = EtoroService()
    service.transaction_repo = mock_repo

    test_date = datetime(2026, 9, 29, 16, 10, 0)
    mock_positions = [
        Position(
            symbol="AMD",
            quantity=0.107006,
            open_price=612.86,
            current_price=615.0,
            market_value=65.8,
            unrealized_pnl=0.28,
            open_date=test_date,
            position_id="3591482503",
        ),
        Position(
            symbol="MU",
            quantity=0.063911,
            open_price=1071.63,
            current_price=1070.0,
            market_value=68.4,
            unrealized_pnl=-0.1,
            open_date=test_date,
            position_id="3591480317",
        ),
    ]
    service.get_positions = AsyncMock(return_value=mock_positions)

    # First run: should backfill both positions as sync_adjustment
    user_id = "00000000-0000-4000-a000-000000000001"
    added_1 = await service._backfill_from_positions(user_id)
    assert added_1 == 2
    assert len(stored_txs) == 2
    assert stored_txs[0].ticker == "AMD"
    assert stored_txs[0].entry_category == "sync_adjustment"
    assert stored_txs[0].source_file == "etoro_pos_3591482503"
    assert stored_txs[1].ticker == "MU"
    assert stored_txs[1].entry_category == "sync_adjustment"

    # Second run: must be completely IDEMPOTENT (0 added)
    added_2 = await service._backfill_from_positions(user_id)
    assert added_2 == 0
    assert len(stored_txs) == 2, "Second run must not insert duplicate transactions"

    # Third run: even if position signature matches from an earlier filled trade
    # Add a mock trade record matching AAPL
    stored_txs.append(
        DummyTx(
            ticker="AAPL",
            action="BUY",
            trade_date="2026-06-18",
            quantity=0.167892,
            price=297.81,
            source_file="eToro",
            raw_data={"broker_trade_info": {"positionExecutions": [{"positionId": "3488214724"}]}},
        )
    )
    mock_positions.append(
        Position(
            symbol="AAPL",
            quantity=0.167892,
            open_price=297.81,
            current_price=300.0,
            market_value=50.3,
            unrealized_pnl=0.3,
            open_date=datetime(2026, 6, 18, 17, 38, 3),
            position_id="3488214724",
        )
    )
    added_3 = await service._backfill_from_positions(user_id)
    assert added_3 == 0, "AAPL already has trade with matching position ID / signature, must not backfill"
    assert len(stored_txs) == 3
