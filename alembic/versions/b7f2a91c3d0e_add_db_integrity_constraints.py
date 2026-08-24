"""add_db_integrity_constraints

Revision ID: b7f2a91c3d0e
Revises: efd641d67adb
Create Date: 2026-04-06 20:40:00.000000

Layer 1 Defense: DB-level CHECK constraints for financial data integrity.

These constraints enforce data validity at the database layer —
the lowest and most reliable line of defense. They fire regardless
of which code path writes to the DB (Python, direct SQL, migrations, etc.).

Constraints added by THIS revision (transactions only):
    chk_tx_action            — action ∈ {BUY, SELL, DEPOSIT, WITHDRAWAL, DIVIDEND, FEE, TAX}
    chk_tx_trade_has_ticker  — BUY/SELL must have non-empty ticker
    chk_tx_qty_positive      — quantity > 0 (corrected by 021; see note below)
    chk_tx_price_nonneg      — price >= 0
    chk_tx_amount_nonneg     — amount >= 0

2026-08-23 correction: this list previously also named
`chk_tx_entry_category` and four `chk_lot_*` constraints on `position_lots`.
The code below never wrote any of them — they were documented and not
implemented. They are installed by `021_backfill_integrity_checks`, which also
backfills the five above onto databases that were stamped past this revision
without ever running it.
本 docstring 原本還列了 entry_category 與四條 position_lots 約束，但程式碼從未寫入；
那些改由 021_backfill_integrity_checks 補上。
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

    # ── transactions constraints ────────────────────────────────────────────

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
    # 2026-08-23: this condition is WRONG but deliberately left as-is.
    #
    # It rejects the DEPOSIT/WITHDRAWAL rows every real deployment holds — cash
    # movements have no instrument and legitimately carry quantity 0. The
    # correct condition exempts `entry_category = 'capital_flow'`, but that
    # column does not exist yet at this point in the chain: `entry_category` is
    # added by `efd641d67adb`, which shares this revision's `down_revision`
    # (879480c2b31c) rather than preceding it, and alembic runs this branch
    # first. Correcting it here makes `alembic upgrade head` fail on a fresh
    # install with `UndefinedColumn`.
    #
    # `021_backfill_integrity_checks` therefore drops and recreates this one
    # constraint with the correct condition, by which point the column exists.
    # No table has rows this early, so the strict form is harmless in between.
    #
    # 此條件是錯的，但刻意保留：entry_category 欄位在鏈上的這個位置還不存在
    # （由 efd641d67adb 新增，而它與本 revision 同一個 down_revision）。
    # 改在這裡會讓全新安裝的 upgrade head 直接失敗，故由 021 重建為正確條件。
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



    # ── Performance index: frequently queried without is_open filter ─────────
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

    # Drop transactions constraints
    _drop_check('transactions', 'chk_tx_amount_nonneg')
    _drop_check('transactions', 'chk_tx_price_nonneg')
    _drop_check('transactions', 'chk_tx_qty_positive')
    _drop_check('transactions', 'chk_tx_trade_has_ticker')
    _drop_check('transactions', 'chk_tx_action')
