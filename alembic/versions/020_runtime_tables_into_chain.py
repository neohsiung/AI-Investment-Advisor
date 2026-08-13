"""runtime_tables_into_chain: put the five repository-created tables under migration control

Five tables were created by application code at runtime rather than by the
chain — `CREATE TABLE IF NOT EXISTS` inside
`src/repositories/ticker_universe_repository.py:25,46,68,83` and
`src/repositories/agent_repository.py:52`. Because no ORM model declared them,
autogenerate reflected them out of the live database, found nothing to match,
and emitted a `drop_table` for each; `alembic/env.py` therefore carried a
`_RUNTIME_MANAGED_TABLES` filter that hid them from the comparison entirely.

That filter's own comment named the price: the tables were outside migration
control, so a change to their DDL in the repositories could never be caught by
CI, and a fresh install created by `alembic upgrade head` got none of them —
they only appeared once some request happened to construct the repository.

This revision closes both gaps together with the ORM models added in
`src/data/models.py`. Column definitions were transcribed from the live
production schema (pg_attribute), not from the repository DDL, so any drift
that had already occurred would be captured rather than papered over; there
was none — `alembic check` reports no operations against production with the
filter removed.

Every statement is guarded, so this revision is a no-op against the existing
production database and only does work on a fresh install.

五張表由 repository 以 `CREATE TABLE IF NOT EXISTS` 在 runtime 建立，既不在
ORM 也不在 migration 鏈中；env.py 因此以過濾器把它們排除在比對之外，代價是
改動其 DDL 不會被 CI 攔到，且 `alembic upgrade head` 建出的新環境根本沒有這些表。
本 revision 與新增的 ORM model 一併補上這兩個缺口。所有語句皆為冪等，對現有
production 為 no-op。

Revision ID: 020_runtime_tables_into_chain
Revises: 019_fresh_install_parity
Create Date: 2026-08-13
"""
from alembic import op

revision = "020_runtime_tables_into_chain"
down_revision = "019_fresh_install_parity"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. ticker_universe — the per-user candidate set the research loop scores.
    op.execute("""
        CREATE TABLE IF NOT EXISTS ticker_universe (
            id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id          UUID NOT NULL,
            ticker           VARCHAR(10) NOT NULL,
            company_name     TEXT,
            sector           VARCHAR(50),
            industry         VARCHAR(50),
            status           VARCHAR(20) DEFAULT 'active',
            added_at         TIMESTAMPTZ DEFAULT NOW(),
            removed_at       TIMESTAMPTZ,
            removal_reason   TEXT,
            last_reviewed_at TIMESTAMPTZ,
            CONSTRAINT ticker_universe_user_id_ticker_key UNIQUE (user_id, ticker)
        );
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_ticker_universe_active
        ON ticker_universe (user_id, status) WHERE status = 'active';
    """)

    # 2. ticker_research — one row per agent per research pass on a ticker.
    op.execute("""
        CREATE TABLE IF NOT EXISTS ticker_research (
            id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id          UUID NOT NULL,
            ticker           VARCHAR(10) NOT NULL,
            agent_name       VARCHAR(50) NOT NULL,
            research_type    VARCHAR(30) NOT NULL,
            confidence_score NUMERIC(5,4),
            target_weight    NUMERIC(5,4),
            expected_return  NUMERIC(8,6),
            risk_score       NUMERIC(5,4),
            thesis           TEXT,
            risks            TEXT[],
            data_sources     JSONB,
            raw_analysis     JSONB,
            created_at       TIMESTAMPTZ DEFAULT NOW()
        );
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_ticker_research_latest
        ON ticker_research (user_id, ticker, created_at DESC);
    """)

    # 3. target_allocations — optimizer output; the weights rebalancing aims at.
    op.execute("""
        CREATE TABLE IF NOT EXISTS target_allocations (
            id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id              UUID NOT NULL,
            ticker               VARCHAR(10) NOT NULL,
            target_weight        NUMERIC(5,4),
            confidence_score     NUMERIC(5,4),
            expected_return      NUMERIC(8,6),
            risk_adjusted_return NUMERIC(8,6),
            min_weight           NUMERIC(5,4),
            max_weight           NUMERIC(5,4),
            last_optimized_at    TIMESTAMPTZ,
            CONSTRAINT target_allocations_user_id_ticker_key UNIQUE (user_id, ticker)
        );
    """)

    # 4. ticker_universe_logs — add/remove audit trail with the agent's reasoning.
    op.execute("""
        CREATE TABLE IF NOT EXISTS ticker_universe_logs (
            id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id    UUID NOT NULL,
            ticker     VARCHAR(10),
            action     VARCHAR(20) NOT NULL,
            agent_name VARCHAR(50),
            reasoning  TEXT,
            old_status VARCHAR(20),
            new_status VARCHAR(20),
            created_at TIMESTAMPTZ DEFAULT NOW()
        );
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_ticker_logs_user
        ON ticker_universe_logs (user_id, created_at DESC);
    """)

    # 5. agent_performance — per-agent success/latency counters driving weights.
    #    Different type family from the four above (TEXT/REAL, un-timezoned
    #    TIMESTAMP, keyed by agent_name); transcribed as it actually exists.
    op.execute("""
        CREATE TABLE IF NOT EXISTS agent_performance (
            agent_name    TEXT PRIMARY KEY,
            tier          TEXT,
            weight        REAL DEFAULT 1.0,
            success_count INTEGER DEFAULT 0,
            failure_count INTEGER DEFAULT 0,
            total_latency REAL DEFAULT 0.0,
            avg_latency   REAL DEFAULT 0.0,
            last_updated  TIMESTAMP
        );
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS ticker_universe_logs;")
    op.execute("DROP TABLE IF EXISTS ticker_research;")
    op.execute("DROP TABLE IF EXISTS target_allocations;")
    op.execute("DROP TABLE IF EXISTS ticker_universe;")
    op.execute("DROP TABLE IF EXISTS agent_performance;")
