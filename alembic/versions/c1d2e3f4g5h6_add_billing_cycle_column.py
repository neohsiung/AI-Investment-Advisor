"""add_billing_cycle_column

Revision ID: c1d2e3f4g5h6
Revises: a02089c0968b
Create Date: 2026-04-13 20:35:00.000000

Add missing current_billing_cycle_start column to users table.
This column tracks when the user's current billing cycle began.
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy import func


revision: str = 'c1d2e3f4g5h6'
down_revision: Union[str, None] = 'a02089c0968b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add the missing column with a safe default
    op.execute(sa.text("""
        ALTER TABLE users
        ADD COLUMN IF NOT EXISTS current_billing_cycle_start TIMESTAMP WITH TIME ZONE
        DEFAULT CURRENT_TIMESTAMP;
    """))


def downgrade() -> None:
    # Remove the column
    op.execute(sa.text("""
        ALTER TABLE users
        DROP COLUMN IF EXISTS current_billing_cycle_start;
    """))
