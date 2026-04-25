"""
tests/unit/repositories/test_transaction_constraints.py
────────────────────────────────────────────────────────
Layer 2 防線：驗證 TransactionRepository.add() 的寫入時校驗邏輯。
"""
import pytest
from unittest.mock import MagicMock, patch
from src.repositories.transaction_repository import (
    AlchemyTransactionRepository,
    ENTRY_CATEGORY_TRADE,
    ENTRY_CATEGORY_CAPITAL_FLOW,
    ENTRY_CATEGORY_SYNC_ADJUSTMENT,
    VALID_ENTRY_CATEGORIES,
)


# ─── Fixture: repo with mocked DB engine ─────────────────────────────────────

@pytest.fixture
def mock_repo():
    """AlchemyTransactionRepository with a fake engine that never writes to DB."""
    with patch("src.repositories.transaction_repository.get_db_engine") as mock_engine_factory:
        mock_engine = MagicMock()
        mock_engine_factory.return_value = mock_engine

        # Make engine.begin() return a no-op context manager
        mock_conn = MagicMock()
        mock_engine.begin.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_engine.begin.return_value.__exit__ = MagicMock(return_value=False)

        repo = AlchemyTransactionRepository(engine=mock_engine)
        yield repo


# ─── Guard 1: entry_category validation ──────────────────────────────────────

def test_add_accepts_all_valid_entry_categories(mock_repo):
    """All three valid entry_category values must pass Guard 1."""
    for cat in [ENTRY_CATEGORY_TRADE, ENTRY_CATEGORY_CAPITAL_FLOW, ENTRY_CATEGORY_SYNC_ADJUSTMENT]:
        action = "DEPOSIT" if cat == ENTRY_CATEGORY_CAPITAL_FLOW else "BUY"
        ticker = "" if cat == ENTRY_CATEGORY_CAPITAL_FLOW else "AAPL"
        # Should NOT raise — just need the guards to pass; DB write is mocked
        try:
            mock_repo.add(
                user_id="u1", ticker=ticker, date="2026-01-01",
                action=action, quantity=1.0, price=100.0, fees=0.0,
                entry_category=cat, amount=100.0,
            )
        except ValueError:
            pytest.fail(f"add() raised ValueError for valid entry_category='{cat}'")


def test_add_rejects_invalid_entry_category(mock_repo):
    """Guard 1: unknown entry_category must raise ValueError with clear message."""
    with pytest.raises(ValueError, match="Invalid entry_category"):
        mock_repo.add(
            user_id="u1", ticker="AAPL", date="2026-01-01",
            action="BUY", quantity=1.0, price=100.0, fees=0.0,
            entry_category="typo_value",
        )


def test_add_rejects_empty_string_entry_category(mock_repo):
    """Guard 1: empty string is not a valid entry_category."""
    with pytest.raises(ValueError, match="Invalid entry_category"):
        mock_repo.add(
            user_id="u1", ticker="AAPL", date="2026-01-01",
            action="BUY", quantity=1.0, price=100.0, fees=0.0,
            entry_category="",
        )


def test_valid_categories_constant_is_complete():
    """Regression: ensure VALID_ENTRY_CATEGORIES contains exactly the three canonical values."""
    assert VALID_ENTRY_CATEGORIES == frozenset({"trade", "capital_flow", "sync_adjustment"})


# ─── Guard 2: BUY/SELL must have a ticker ────────────────────────────────────

def test_add_rejects_buy_without_ticker(mock_repo):
    """Guard 2: BUY with empty ticker must raise ValueError."""
    with pytest.raises(ValueError, match="non-empty ticker"):
        mock_repo.add(
            user_id="u1", ticker="", date="2026-01-01",
            action="BUY", quantity=1.0, price=100.0, fees=0.0,
            entry_category=ENTRY_CATEGORY_TRADE,
        )


def test_add_rejects_sell_without_ticker(mock_repo):
    """Guard 2: SELL with whitespace-only ticker must raise ValueError."""
    with pytest.raises(ValueError, match="non-empty ticker"):
        mock_repo.add(
            user_id="u1", ticker="   ", date="2026-01-01",
            action="SELL", quantity=1.0, price=100.0, fees=0.0,
            entry_category=ENTRY_CATEGORY_TRADE,
        )


def test_add_accepts_buy_with_valid_ticker(mock_repo):
    """Guard 2: BUY with a real ticker must pass."""
    try:
        mock_repo.add(
            user_id="u1", ticker="NVDA", date="2026-01-01",
            action="BUY", quantity=5.0, price=800.0, fees=0.0,
            entry_category=ENTRY_CATEGORY_TRADE,
        )
    except ValueError as e:
        pytest.fail(f"Unexpectedly raised ValueError: {e}")


def test_add_deposit_without_ticker_is_allowed(mock_repo):
    """Guard 2: DEPOSIT (capital_flow) with ticker='USD' or empty is fine — no ticker guard."""
    try:
        mock_repo.add(
            user_id="u1", ticker="USD", date="2026-01-01",
            action="DEPOSIT", quantity=1.0, price=500.0, fees=0.0,
            entry_category=ENTRY_CATEGORY_CAPITAL_FLOW,
            amount=500.0,
        )
    except ValueError as e:
        pytest.fail(f"Unexpectedly raised ValueError for DEPOSIT: {e}")


# ─── Guard 3: capital_flow must use DEPOSIT/WITHDRAWAL with amount > 0 ───────

def test_add_rejects_capital_flow_with_buy_action(mock_repo):
    """Guard 3: capital_flow must not use BUY action."""
    with pytest.raises(ValueError, match="capital_flow entry must use action DEPOSIT or WITHDRAWAL"):
        mock_repo.add(
            user_id="u1", ticker="AAPL", date="2026-01-01",
            action="BUY", quantity=1.0, price=500.0, fees=0.0,
            entry_category=ENTRY_CATEGORY_CAPITAL_FLOW,
        )


def test_add_rejects_capital_flow_with_zero_amount(mock_repo):
    """Guard 3: capital_flow with derived amount = 0 must raise."""
    with pytest.raises(ValueError, match="amount > 0"):
        mock_repo.add(
            user_id="u1", ticker="USD", date="2026-01-01",
            action="DEPOSIT", quantity=1.0, price=0.0, fees=0.0,
            entry_category=ENTRY_CATEGORY_CAPITAL_FLOW,
        )


def test_add_rejects_capital_flow_with_explicit_zero_amount(mock_repo):
    """Guard 3: explicitly passing amount=0.0 must raise."""
    with pytest.raises(ValueError, match="amount > 0"):
        mock_repo.add(
            user_id="u1", ticker="USD", date="2026-01-01",
            action="DEPOSIT", quantity=1.0, price=100.0, fees=0.0,
            entry_category=ENTRY_CATEGORY_CAPITAL_FLOW,
            amount=0.0,
        )


def test_add_capital_flow_accepts_valid_deposit(mock_repo):
    """Guard 3: DEPOSIT with positive amount must pass all guards."""
    try:
        mock_repo.add(
            user_id="u1", ticker="USD", date="2026-01-01",
            action="DEPOSIT", quantity=1.0, price=1500.0, fees=0.0,
            entry_category=ENTRY_CATEGORY_CAPITAL_FLOW,
            amount=1500.0,
        )
    except ValueError as e:
        pytest.fail(f"Valid capital_flow DEPOSIT raised ValueError: {e}")


def test_add_capital_flow_accepts_withdrawal(mock_repo):
    """Guard 3: WITHDRAWAL capital_flow must also pass guards."""
    try:
        mock_repo.add(
            user_id="u1", ticker="USD", date="2026-01-01",
            action="WITHDRAWAL", quantity=1.0, price=200.0, fees=0.0,
            entry_category=ENTRY_CATEGORY_CAPITAL_FLOW,
            amount=200.0,
        )
    except ValueError as e:
        pytest.fail(f"Valid capital_flow WITHDRAWAL raised ValueError: {e}")


# ─── Amount override ──────────────────────────────────────────────────────────

def test_explicit_amount_overrides_derived_amount(mock_repo):
    """
    When amount is explicitly provided, it should be used as-is instead of
    computing price * quantity / leverage.
    """
    # price=50, qty=2 → derived would be 100, but we override to 999
    # No error should be raised — the validation only checks amount > 0 for capital_flow
    try:
        mock_repo.add(
            user_id="u1", ticker="AAPL", date="2026-01-01",
            action="BUY", quantity=2.0, price=50.0, fees=0.0,
            entry_category=ENTRY_CATEGORY_TRADE,
            amount=999.0,
        )
    except ValueError as e:
        pytest.fail(f"Explicit amount override raised unexpected ValueError: {e}")
