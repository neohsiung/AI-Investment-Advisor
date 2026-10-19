"""032_charter_events: append-only audit log of the charter change engine (G6/G9)

Revision ID: 032_charter_events
Revises: 031_rotation_pair_observations
Create Date: 2026-10-19

Additive only: one new table. 僅新增一張表。
"""
from alembic import op

revision = "032_charter_events"
down_revision = "031_rotation_pair_observations"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS charter_events (
            id BIGSERIAL PRIMARY KEY,
            user_id VARCHAR NOT NULL,
            kind VARCHAR(16) NOT NULL,
            key VARCHAR(128),
            payload_json JSON,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT ck_charter_events_kind CHECK (kind IN
                ('verdict', 'apply', 'rollback', 'freeze', 'resume', 'degrade', 'digest', 'drill', 'enable'))
        );
        CREATE INDEX IF NOT EXISTS ix_charter_events_user_kind_created ON charter_events (user_id, kind, created_at);
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS charter_events;")
