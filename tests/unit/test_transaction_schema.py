"""
Unit tests for TransactionRecord schema validation.
Tests the fix for DEPOSIT transactions with quantity=0, price=0.
"""
import pytest
from pydantic import ValidationError
from src.api.v1.schemas.transaction_schemas import (
    TransactionRecord, TransactionCreateRequest, TransactionBase
)


class TestTransactionBase:
    """TransactionBase schema validation tests."""

    def test_normal_buy_passes(self):
        """A normal BUY with positive qty and price should pass."""
        tx = TransactionBase(
            ticker="AAPL",
            action="BUY",
            quantity=10.0,
            price=150.0,
            date="2026-06-01"
        )
        assert tx.quantity == 10.0
        assert tx.price == 150.0
        assert tx.ticker == "AAPL"
        assert tx.action == "BUY"

    def test_deposit_with_zero_qty_price_passes(self):
        """
        DEPOSIT transactions have quantity=0 and price=0.
        After fix (ge=0 instead of gt=0), this should pass.
        """
        tx = TransactionBase(
            ticker="CASH",
            action="DEPOSIT",
            quantity=0.0,
            price=0.0,
            date="2026-06-14"
        )
        assert tx.quantity == 0.0
        assert tx.price == 0.0

    def test_negative_quantity_still_rejected(self):
        """Negative quantity should still be rejected."""
        with pytest.raises(ValidationError) as exc:
            TransactionBase(
                ticker="AAPL",
                action="BUY",
                quantity=-1.0,
                price=150.0,
                date="2026-06-01"
            )
        assert "quantity" in str(exc.value)

    def test_negative_price_still_rejected(self):
        """Negative price should still be rejected."""
        with pytest.raises(ValidationError) as exc:
            TransactionBase(
                ticker="AAPL",
                action="BUY",
                quantity=10.0,
                price=-1.0,
                date="2026-06-01"
            )
        assert "price" in str(exc.value)

    def test_ticker_auto_uppercase(self):
        """Ticker should be auto-converted to uppercase."""
        tx = TransactionBase(
            ticker="aapl",
            action="buy",
            quantity=10.0,
            price=150.0,
            date="2026-06-01"
        )
        assert tx.ticker == "AAPL"
        assert tx.action == "BUY"


class TestTransactionRecord:
    """TransactionRecord schema tests."""

    def test_record_with_zero_values(self):
        """TransactionRecord should accept qty=0, price=0 for DEPOSIT."""
        record = TransactionRecord(
            id="test-id-123",
            ticker="CASH",
            action="DEPOSIT",
            quantity=0.0,
            price=0.0,
            date="2026-06-14"
        )
        assert record.quantity == 0.0
        assert record.price == 0.0
        assert record.id == "test-id-123"

    def test_record_with_normal_values(self):
        """TransactionRecord with normal BUY values."""
        record = TransactionRecord(
            id="test-id-456",
            ticker="AAPL",
            action="BUY",
            quantity=10.0,
            price=150.0,
            date="2026-06-01"
        )
        assert record.quantity == 10.0
        assert record.price == 150.0


class TestTransactionCreateRequest:
    """TransactionCreateRequest schema tests."""

    def test_create_request_with_zero_values(self):
        """Create request should also accept qty=0, price=0."""
        req = TransactionCreateRequest(
            ticker="CASH",
            action="DEPOSIT",
            quantity=0.0,
            price=0.0,
            date="2026-06-14"
        )
        assert req.quantity == 0.0
        assert req.price == 0.0