"""backfill_integrity_checks: put the CHECK constraints on databases that were stamped past them

`b7f2a91c3d0e` (2026-04-06) was supposed to install the Layer 1 integrity
constraints. Production's `alembic_version` is well past it — yet
`pg_constraint` returns **zero** CHECK constraints on `transactions` and
`position_lots`. The revision never ran there: prod's schema was built with
`create_all()` and then stamped, the same history that
`019_fresh_install_parity` and `020_runtime_tables_into_chain` were written
to clean up (see `scripts/init_db.py`).

Nothing failed as a result, which is exactly why it went unnoticed for four
months. It surfaced on 2026-08-23 only because `19e67a89` declared the
constraints on the ORM model, at which point `alembic check` against
production went from 0 diffs to 6.

Two further gaps found while writing this:

1. `b7f2a91c3d0e`'s docstring lists ten constraints; its code adds five.
   `chk_tx_entry_category` and the four `chk_lot_*` were documented and never
   written. This revision adds them, using the names the ORM declares
   (`transactions_entry_category_check`) so `alembic check` converges to zero.

2. `chk_tx_qty_positive` was an unconditional `quantity > 0`, which no real
   deployment can satisfy: DEPOSIT/WITHDRAWAL rows are cash movements with no
   instrument and legitimately carry quantity 0 (10 such rows in production).
   This revision drops and recreates it with the `entry_category =
   'capital_flow'` exemption. It could not simply be corrected in place in
   `b7f2a91c3d0e`: `entry_category` is added by `efd641d67adb`, which shares
   that revision's `down_revision` rather than preceding it, so alembic runs
   the constraint branch first and a corrected condition there fails a fresh
   install with `UndefinedColumn`. Verified by running the full chain against
   an empty pgvector container.

Verified against production before writing (read-only counts): 0 rows violate
any of these ten conditions under the corrected definitions.

每個語句都是冪等的：約束已存在就跳過，因此對已補齊的資料庫是 no-op。

Revision ID: 021_backfill_integrity_checks
Revises: 020_runtime_tables_into_chain
Create Date: 2026-08-23
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = '021_backfill_integrity_checks'
down_revision: Union[str, None] = '020_runtime_tables_into_chain'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Same guarded helper as b7f2a91c3d0e — repeated rather than imported so the
# revision stays self-contained and readable on its own.
# 與 b7f2a91c3d0e 相同的冪等 helper，刻意重複而非 import，讓 revision 自成一體。
def _add_check(table: str, name: str, condition: str) -> None:
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
    op.execute(sa.text(f'ALTER TABLE {table} DROP CONSTRAINT IF EXISTS {name}'))


# The six declared on `Transaction.__table_args__` in src/data/models.py.
# Conditions must match the ORM text exactly, or `alembic check` keeps
# reporting a diff.
# 條件文字必須與 ORM 宣告一致，否則 alembic check 會持續回報差異。
_TRANSACTION_CHECKS = (
    (
        'chk_tx_action',
        "action IN ('BUY', 'SELL', 'DEPOSIT', 'WITHDRAWAL', 'DIVIDEND', 'FEE', 'TAX')",
    ),
    (
        'chk_tx_trade_has_ticker',
        "action NOT IN ('BUY', 'SELL') OR (ticker IS NOT NULL AND TRIM(ticker) <> '')",
    ),
    (
        'chk_tx_qty_positive',
        "quantity > 0 OR entry_category = 'capital_flow'",
    ),
    ('chk_tx_price_nonneg', 'price >= 0'),
    ('chk_tx_amount_nonneg', 'amount >= 0'),
    (
        'transactions_entry_category_check',
        "entry_category IN ('trade', 'capital_flow', 'sync_adjustment')",
    ),
)

# The four b7f2a91c3d0e documented but never wrote. Production holds 18 lots,
# none of which violate any of them.
# b7f2a91c3d0e 只寫在 docstring 裡、從未實作的四條。
_POSITION_LOT_CHECKS = (
    ('chk_lot_qty_positive', 'quantity > 0'),
    ('chk_lot_open_price_pos', 'open_price > 0'),
    ('chk_lot_close_price_pos', 'close_price IS NULL OR close_price > 0'),
    ('chk_lot_leverage_pos', 'leverage IS NULL OR leverage >= 1.0'),
)


def upgrade() -> None:
    # Drop first, then add: a fresh install already carries the strict
    # `quantity > 0` form installed by b7f2a91c3d0e, and `_add_check` skips
    # anything that already exists by name. Only this one needs replacing.
    # 先 drop 再 add：全新安裝已帶著 b7f2a91c3d0e 的嚴格版本，而 _add_check
    # 見到同名約束就會跳過，因此只有這一條需要替換。
    _drop_check('transactions', 'chk_tx_qty_positive')

    for name, condition in _TRANSACTION_CHECKS:
        _add_check('transactions', name, condition)

    for name, condition in _POSITION_LOT_CHECKS:
        _add_check('position_lots', name, condition)


def downgrade() -> None:
    for name, _ in _POSITION_LOT_CHECKS:
        _drop_check('position_lots', name)

    # Leave the five from b7f2a91c3d0e in place on downgrade — that revision
    # owns them and drops them itself. Only the constraint this revision
    # introduced on `transactions` is removed here.
    # 其餘五條由 b7f2a91c3d0e 自行負責，此處只移除本 revision 新增的那一條。
    _drop_check('transactions', 'transactions_entry_category_check')
