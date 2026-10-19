"""029_threshold_band_observations: every signal near a threshold, with score and threshold in force (G1)

Revision ID: 029_threshold_band_observations
Revises: 027_trade_proposals
Create Date: 2026-10-19

Additive only: one new table, no change to existing tables. Recording evidence for the parameter registry.
僅新增一張表，不動既有表；為參數登錄檔保存門檻帶證據。
"""
from alembic import op

revision = "029_threshold_band_observations"
down_revision = "027_trade_proposals"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS threshold_band_observations (
            id VARCHAR PRIMARY KEY,
            user_id VARCHAR NOT NULL,
            threshold_key VARCHAR NOT NULL,
            source_service VARCHAR NOT NULL,
            ticker VARCHAR NOT NULL,
            direction VARCHAR(4) NOT NULL,
            obs_date DATE NOT NULL,
            score NUMERIC(10, 4),
            threshold_value NUMERIC(10, 4) NOT NULL,
            margin NUMERIC(10, 4),
            passed BOOLEAN,
            in_band BOOLEAN NOT NULL,
            price NUMERIC(18, 8),
            data_marker VARCHAR,
            context TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT uq_threshold_band_obs
                UNIQUE (user_id, threshold_key, source_service, ticker, direction, obs_date)
        );
        CREATE INDEX IF NOT EXISTS ix_threshold_band_obs_key_date
            ON threshold_band_observations (threshold_key, obs_date);
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS threshold_band_observations;")
