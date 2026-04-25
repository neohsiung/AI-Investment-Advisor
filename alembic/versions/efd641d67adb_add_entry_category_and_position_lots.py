"""add_entry_category_and_position_lots

Revision ID: efd641d67adb
Revises: 879480c2b31c
Create Date: 2026-04-06 16:30:00.000000

Phase 1: Add entry_category TEXT column to transactions.
Phase 3: Create position_lots table for O(1) avg_cost lookup.

entry_category values:
  'trade'            — Regular BUY / SELL / DIVIDEND / FEE / TAX
  'capital_flow'     — Real user deposits / withdrawals
  'sync_adjustment'  — Synthetic ETORO_SYNC balancing entries (not real money)
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'efd641d67adb'
down_revision: Union[str, None] = '879480c2b31c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ------------------------------------------------------------------ #
    # Phase 1: Add entry_category column to transactions
    # ------------------------------------------------------------------ #

    # 1a. Add column with default 'trade' so existing rows are non-NULL
    op.execute(sa.text("""
        ALTER TABLE transactions
          ADD COLUMN IF NOT EXISTS entry_category TEXT NOT NULL DEFAULT 'trade'
          CHECK (entry_category IN ('trade', 'capital_flow', 'sync_adjustment'))
    """))

    # 1b. Backfill: ETORO_SYNC entries → sync_adjustment
    op.execute(sa.text("""
        UPDATE transactions
          SET entry_category = 'sync_adjustment'
          WHERE source_file = 'ETORO_SYNC'
    """))

    # 1c. Backfill: real user deposits / withdrawals → capital_flow
    #     (Only those NOT from ETORO_SYNC, which were already marked above)
    op.execute(sa.text("""
        UPDATE transactions
          SET entry_category = 'capital_flow'
          WHERE action IN ('DEPOSIT', 'WITHDRAWAL')
            AND entry_category = 'trade'
    """))

    # ------------------------------------------------------------------ #
    # Phase 3: Create position_lots table
    # ------------------------------------------------------------------ #
    op.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS position_lots (
            id            TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
            user_id       TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            ticker        TEXT NOT NULL,
            open_date     TEXT NOT NULL,
            close_date    TEXT,
            quantity      FLOAT NOT NULL,
            open_price    FLOAT NOT NULL,
            close_price   FLOAT,
            leverage      FLOAT DEFAULT 1.0,
            is_open       BOOLEAN DEFAULT TRUE,
            source_tx_id  TEXT REFERENCES transactions(id) ON DELETE SET NULL,
            created_at    TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
        )
    """))

    # Indexes for O(1) lookup patterns used by get_holdings() and PnLCalculator
    op.execute(sa.text("""
        CREATE INDEX IF NOT EXISTS idx_position_lots_user_open
          ON position_lots (user_id, is_open)
    """))
    op.execute(sa.text("""
        CREATE INDEX IF NOT EXISTS idx_position_lots_user_ticker
          ON position_lots (user_id, ticker)
    """))


def downgrade() -> None:
    # Phase 3 rollback
    op.execute(sa.text('DROP INDEX IF EXISTS idx_position_lots_user_ticker'))
    op.execute(sa.text('DROP INDEX IF EXISTS idx_position_lots_user_open'))
    op.execute(sa.text('DROP TABLE IF EXISTS position_lots'))

    # Phase 1 rollback — PostgreSQL 15+ supports DROP COLUMN IF EXISTS
    op.execute(sa.text('ALTER TABLE transactions DROP COLUMN IF EXISTS entry_category'))
