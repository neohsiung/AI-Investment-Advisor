"""029_parameter_proposals: proposals to change settings, written by tuning loops instead of live writes

Revision ID: 029_parameter_proposals
Revises: 028_parameter_store
Create Date: 2026-10-19
"""
from alembic import op

revision = "029_parameter_proposals"
down_revision = "028_parameter_store"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS parameter_proposals (
            id VARCHAR PRIMARY KEY,
            user_id VARCHAR NOT NULL,
            source VARCHAR(32) NOT NULL,
            proposed_values TEXT NOT NULL,
            evidence TEXT,
            status VARCHAR(16) NOT NULL DEFAULT 'proposed',
            idempotency_key VARCHAR(128) NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            decided_at TIMESTAMPTZ,
            CONSTRAINT ck_parameter_proposals_status
                CHECK (status IN ('proposed', 'approved', 'rejected', 'applied', 'expired')),
            CONSTRAINT uq_parameter_proposals_idempotency UNIQUE (user_id, source, idempotency_key)
        );
        CREATE INDEX IF NOT EXISTS ix_parameter_proposals_user_created
            ON parameter_proposals (user_id, created_at);
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS parameter_proposals;")
