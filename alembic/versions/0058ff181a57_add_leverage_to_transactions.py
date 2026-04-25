"""add_leverage_to_transactions

Revision ID: 0058ff181a57
Revises: c1d2e3f4g5h6
Create Date: 2026-04-12 07:54:44.006221

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0058ff181a57'
down_revision: Union[str, Sequence[str], None] = 'c1d2e3f4g5h6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute(sa.text("ALTER TABLE transactions ADD COLUMN IF NOT EXISTS leverage NUMERIC(18, 8) DEFAULT 1.0;"))



def downgrade() -> None:
    """Downgrade schema."""
    op.execute(sa.text("ALTER TABLE transactions DROP COLUMN IF EXISTS leverage;"))

