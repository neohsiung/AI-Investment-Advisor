"""030_rotation_pair_observations: one record per rotation decision linking sell and buy legs (G1b)

Revision ID: 030_rotation_pair_observations
Revises: 028_parameter_store, 028_parameter_proposals
Create Date: 2026-10-19

Additive only: one new table. 僅新增一張表。
"""
from alembic import op

revision = "030_rotation_pair_observations"
down_revision = ("028_parameter_store", "028_parameter_proposals")  # also merges the two 028 heads / 同時合併兩個 028 head
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS rotation_pair_observations (
            id VARCHAR PRIMARY KEY,
            user_id VARCHAR NOT NULL,
            obs_date DATE NOT NULL,
            sell_ticker VARCHAR NOT NULL,
            buy_ticker VARCHAR NOT NULL,
            decision VARCHAR NOT NULL,
            holding_score NUMERIC(10, 4),
            candidate_score NUMERIC(10, 4),
            score_delta NUMERIC(10, 4),
            holding_age_days NUMERIC(10, 4),
            min_score_delta NUMERIC(10, 4) NOT NULL,
            min_holding_days NUMERIC(10, 4) NOT NULL,
            friction_pct NUMERIC(10, 4),
            sell_price NUMERIC(18, 8),
            buy_price NUMERIC(18, 8),
            data_marker VARCHAR,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT uq_rotation_pair_obs UNIQUE (user_id, sell_ticker, buy_ticker, obs_date, decision)
        );
        CREATE INDEX IF NOT EXISTS ix_rotation_pair_obs_date ON rotation_pair_observations (obs_date);
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS rotation_pair_observations;")
