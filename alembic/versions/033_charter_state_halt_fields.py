"""033_charter_state_halt_fields: halt bookkeeping columns on charter_state (G7)

Revision ID: 033_charter_state_halt_fields
Revises: 032_charter_events
Create Date: 2026-10-20

Additive only: four nullable columns, no defaults, existing rows untouched. Writers set them explicitly.
僅新增四個可為空的欄位，無預設值；既有列不變，寫入者顯式指定。
"""
from alembic import op

revision = "033_charter_state_halt_fields"
down_revision = "032_charter_events"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE charter_state
            ADD COLUMN IF NOT EXISTS clears_on DATE,
            ADD COLUMN IF NOT EXISTS breach_ids JSON,
            ADD COLUMN IF NOT EXISTS resume_mode VARCHAR(16),
            ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ;
    """)


def downgrade() -> None:
    op.execute("""
        ALTER TABLE charter_state
            DROP COLUMN IF EXISTS updated_at,
            DROP COLUMN IF EXISTS resume_mode,
            DROP COLUMN IF EXISTS breach_ids,
            DROP COLUMN IF EXISTS clears_on;
    """)
