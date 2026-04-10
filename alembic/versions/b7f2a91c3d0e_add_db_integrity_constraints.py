"""add_db_integrity_constraints

Revision ID: b7f2a91c3d0e
Revises: efd641d67adb
Create Date: 2026-04-06 20:40:00.000000

Layer 1 Defense: DB-level CHECK constraints for financial data integrity.

These constraints enforce data validity at the database layer —
the lowest and most reliable line of defense. They fire regardless
of which code path writes to the DB (Python, direct SQL, migrations, etc.).

Constraints added:
  transactions:
    chk_tx_entry_category    — entry_category ∈ {trade, capital_flow, sync_adjustment}
    chk_tx_action            — action ∈ {BUY, SELL, DEPOSIT, WITHDRAWAL, DIVIDEND, FEE, TAX}
    chk_tx_trade_has_ticker  — BUY/SELL must have non-empty ticker
    chk_tx_qty_positive      — quantity > 0
    chk_tx_price_nonneg      — price >= 0
    chk_tx_amount_nonneg     — amount >= 0

  position_lots:
    chk_lot_qty_positive     — quantity > 0
    chk_lot_open_price_pos   — open_price > 0
    chk_lot_close_price_pos  — close_price > 0 (when not NULL)
    chk_lot_leverage_pos     — leverage >= 1.0 (no sub-1 leverage)
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = 'b7f2a91c3d0e'
down_revision: Union[str, None] = '879480c2b31c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _add_check(table: str, name: str, condition: str) -> None:
    """Add a named CHECK constraint, skipping if it already exists."""
    op.execute(sa.text(f"""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint c
                JOIN pg_class r ON r.oid = c.conrelid
                WHERE r.relname = '{table}' AND c.conname = '{name}'
            ) THEN
                ALTER TABLE {table}
                    ADD CONSTRAINT {name} CHECK ({condition});
            END IF;
        END
        $$;
    """))


def _drop_check(table: str, name: str) -> None:
    """Drop a named CHECK constraint if it exists."""
    op.execute(sa.text(f"""
        ALTER TABLE {table} DROP CONSTRAINT IF EXISTS {name};
    """))


# ---------------------------------------------------------------------------
# Upgrade
# ---------------------------------------------------------------------------

def upgrade() -> None:
    # ── Pre-flight: sanitize any existing bad data so constraints don't fail ──

    # Normalise action values to uppercase (should already be correct, but be safe)
    op.execute(sa.text("""
        UPDATE transactions SET action = UPPER(action)
        WHERE action != UPPER(action);
    """))

    # Ensure entry_category is set on all rows
    op.execute(sa.text("""
        UPDATE transactions
        SET entry_category = 'trade'
        WHERE entry_category IS NULL OR entry_category NOT IN ('trade', 'capital_flow', 'sync_adjustment');
    """))

    # ── transactions constraints ────────────────────────────────────────────

    # 1. entry_category must be one of the three canonical values
    _add_check(
        'transactions',
        'chk_tx_entry_category',
        "entry_category IN ('trade', 'capital_flow', 'sync_adjustment')",
    )

    # 2. action must be a recognised financial operation
    _add_check(
        'transactions',
        'chk_tx_action',
        "action IN ('BUY', 'SELL', 'DEPOSIT', 'WITHDRAWAL', 'DIVIDEND', 'FEE', 'TAX')",
    )

    # 3. BUY and SELL must have a non-empty ticker
    #    (DEPOSIT/WITHDRAWAL use ticker='CASH' or 'USD', which is fine)
    _add_check(
        'transactions',
        'chk_tx_trade_has_ticker',
        """
        action NOT IN ('BUY', 'SELL')
        OR (ticker IS NOT NULL AND TRIM(ticker) <> '')
        """,
    )

    # 4. quantity must be positive (can't buy 0 or negative shares)
    _add_check(
        'transactions',
        'chk_tx_qty_positive',
        'quantity > 0',
    )

    # 5. price must be non-negative (free dividend/fee events are valid at price=0)
    _add_check(
        'transactions',
        'chk_tx_price_nonneg',
        'price >= 0',
    )

    # 6. amount must be non-negative
    _add_check(
        'transactions',
        'chk_tx_amount_nonneg',
        'amount >= 0',
    )

    # ── position_lots constraints ───────────────────────────────────────────

    # 7. Lot quantity must be positive — zero or negative lots are invalid
    _add_check(
        'position_lots',
        'chk_lot_qty_positive',
        'quantity > 0',
    )

    # 8. open_price must be positive — can't open a lot at free or negative price
    _add_check(
        'position_lots',
        'chk_lot_open_price_pos',
        'open_price > 0',
    )

    # 9. close_price, when provided, must be positive
    _add_check(
        'position_lots',
        'chk_lot_close_price_pos',
        'close_price IS NULL OR close_price > 0',
    )

    # 10. leverage must be >= 1.0 (no fractional leverage; 1.0 = no leverage)
    _add_check(
        'position_lots',
        'chk_lot_leverage_pos',
        'leverage IS NULL OR leverage >= 1.0',
    )

    # ── Performance index: frequently queried without is_open filter ─────────
    op.execute(sa.text("""
        CREATE INDEX IF NOT EXISTS idx_transactions_user_category
            ON transactions (user_id, entry_category);
    """))

    op.execute(sa.text("""
        CREATE INDEX IF NOT EXISTS idx_transactions_user_date
            ON transactions (user_id, trade_date DESC);
    """))


# ---------------------------------------------------------------------------
# Downgrade
# ---------------------------------------------------------------------------

def downgrade() -> None:
    # Drop indexes
    op.execute(sa.text('DROP INDEX IF EXISTS idx_transactions_user_date'))
    op.execute(sa.text('DROP INDEX IF EXISTS idx_transactions_user_category'))

    # Drop position_lots constraints
    _drop_check('position_lots', 'chk_lot_leverage_pos')
    _drop_check('position_lots', 'chk_lot_close_price_pos')
    _drop_check('position_lots', 'chk_lot_open_price_pos')
    _drop_check('position_lots', 'chk_lot_qty_positive')

    # Drop transactions constraints
    _drop_check('transactions', 'chk_tx_amount_nonneg')
    _drop_check('transactions', 'chk_tx_price_nonneg')
    _drop_check('transactions', 'chk_tx_qty_positive')
    _drop_check('transactions', 'chk_tx_trade_has_ticker')
    _drop_check('transactions', 'chk_tx_action')
    _drop_check('transactions', 'chk_tx_entry_category')
