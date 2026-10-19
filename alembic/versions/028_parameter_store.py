"""028_parameter_store: charter parameter store (values, trials, changes, charter_state)

Additive only; nothing in the trading path reads these tables until milestone G10.
僅新增資料表；G10 之前交易路徑不讀取。

Revision ID: 028_parameter_store
Revises: 027_trade_proposals
Create Date: 2026-10-19
"""
from alembic import op

revision = "028_parameter_store"
down_revision = "027_trade_proposals"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS parameter_changes (
            id BIGSERIAL PRIMARY KEY,
            key VARCHAR(128) NOT NULL,
            from_value_json JSON,
            to_value_json JSON,
            direction VARCHAR(8) NOT NULL,
            test_statistic NUMERIC(18, 6),
            window_series_json JSON,
            verdict VARCHAR(16) NOT NULL,
            applied_at TIMESTAMPTZ,
            rolled_back_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT ck_parameter_changes_direction CHECK (direction IN ('tighten', 'loosen'))
        );
        CREATE INDEX IF NOT EXISTS ix_parameter_changes_key_created ON parameter_changes (key, created_at);

        CREATE TABLE IF NOT EXISTS parameter_values (
            id BIGSERIAL PRIMARY KEY,
            key VARCHAR(128) NOT NULL,
            version INTEGER NOT NULL,
            value_json JSON NOT NULL,
            effective_from TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            source VARCHAR(8) NOT NULL,
            change_id BIGINT REFERENCES parameter_changes (id),
            CONSTRAINT ck_parameter_values_source CHECK (source IN ('seed', 'engine', 'human', 'rollback')),
            CONSTRAINT uq_parameter_values_key_version UNIQUE (key, version)
        );

        CREATE TABLE IF NOT EXISTS parameter_trials (
            id BIGSERIAL PRIMARY KEY,
            key VARCHAR(128) NOT NULL,
            grid_value NUMERIC(18, 6) NOT NULL,
            n_cum INTEGER NOT NULL,
            registered_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT uq_parameter_trials_key_value UNIQUE (key, grid_value)
        );

        CREATE TABLE IF NOT EXISTS charter_state (
            id INTEGER PRIMARY KEY,
            mode VARCHAR(16) NOT NULL DEFAULT 'dry_run',
            reason TEXT,
            since TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            human_stop BOOLEAN NOT NULL DEFAULT false,
            CONSTRAINT ck_charter_state_singleton CHECK (id = 1),
            CONSTRAINT ck_charter_state_mode
                CHECK (mode IN ('dry_run', 'apply', 'tighten_only', 'frozen', 'human_stop'))
        );
        INSERT INTO charter_state (id, mode, reason) VALUES (1, 'dry_run', 'initial: engine not built')
            ON CONFLICT (id) DO NOTHING;
    """)


def downgrade() -> None:
    op.execute("""
        DROP TABLE IF EXISTS charter_state;
        DROP TABLE IF EXISTS parameter_trials;
        DROP TABLE IF EXISTS parameter_values;
        DROP TABLE IF EXISTS parameter_changes;
    """)
