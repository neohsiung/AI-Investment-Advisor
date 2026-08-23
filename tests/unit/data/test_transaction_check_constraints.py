"""
The Layer 1 CHECK constraints must stay declarable AND appliable.

2026-08-23: production held **zero** CHECK constraints on `transactions` and
`position_lots` while `alembic_version` sat well past `b7f2a91c3d0e`, the
revision that was supposed to install them — prod's schema came from
`create_all()` + stamp, so the revision never ran. Nothing failed; the absence
was invisible until `19e67a89` declared the constraints on the ORM and
`alembic check` went from 0 diffs to 6.

The correction that mattered: `chk_tx_qty_positive` was an unconditional
`quantity > 0`, which no real database can satisfy. DEPOSIT/WITHDRAWAL rows are
cash movements with no instrument and legitimately carry quantity 0 (10 such
rows in production). These tests pin the exemption so it cannot quietly revert
to the unappliable form.

生產環境的 CHECK 約束一條都不存在，而 chk_tx_qty_positive 的原始條件
（無條件 quantity > 0）會擋掉合法的現金流列，任何真實資料庫都套用不上。
"""
import pytest
from sqlalchemy import CheckConstraint

from src.data.models import PositionLot, Transaction


def _checks(model):
    return {
        c.name: str(c.sqltext)
        for c in model.__table__.constraints
        if isinstance(c, CheckConstraint)
    }


class TestTransactionChecks:
    def test_qty_constraint_exempts_capital_flow(self):
        """A DEPOSIT carries quantity 0 by nature — the constraint must allow it."""
        condition = _checks(Transaction)['chk_tx_qty_positive']

        assert "capital_flow" in condition, (
            "chk_tx_qty_positive must exempt capital_flow rows; the "
            "unconditional `quantity > 0` form cannot be applied to any "
            "database that has ever recorded a deposit or withdrawal"
        )

    @pytest.mark.parametrize("name", [
        'chk_tx_action',
        'chk_tx_trade_has_ticker',
        'chk_tx_qty_positive',
        'chk_tx_price_nonneg',
        'chk_tx_amount_nonneg',
        'transactions_entry_category_check',
    ])
    def test_declared(self, name):
        assert name in _checks(Transaction)


class TestPositionLotChecks:
    @pytest.mark.parametrize("name", [
        'chk_lot_qty_positive',
        'chk_lot_open_price_pos',
        'chk_lot_close_price_pos',
        'chk_lot_leverage_pos',
    ])
    def test_declared(self, name):
        """b7f2a91c3d0e's docstring promised these four; its code never wrote
        them. They are declared here and installed by 021."""
        assert name in _checks(PositionLot)

    def test_nullable_columns_are_not_rejected_when_null(self):
        checks = _checks(PositionLot)

        assert "IS NULL" in checks['chk_lot_close_price_pos']
        assert "IS NULL" in checks['chk_lot_leverage_pos']


class TestMigrationMatchesOrm:
    """The migration's condition text must match the ORM's, or `alembic check`
    reports a diff forever. 條件文字不一致，alembic check 會永遠回報差異。"""

    def test_condition_text_is_identical(self):
        import importlib.util
        from pathlib import Path

        path = Path(__file__).resolve().parents[3] / "alembic" / "versions" / "021_backfill_integrity_checks.py"
        spec = importlib.util.spec_from_file_location("rev021", path)
        rev = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(rev)

        orm_tx = _checks(Transaction)
        for name, condition in rev._TRANSACTION_CHECKS:
            assert orm_tx[name] == condition, f"{name} drifted between ORM and migration"

        orm_lot = _checks(PositionLot)
        for name, condition in rev._POSITION_LOT_CHECKS:
            assert orm_lot[name] == condition, f"{name} drifted between ORM and migration"
