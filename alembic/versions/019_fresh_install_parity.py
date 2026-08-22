"""fresh_install_parity: make a from-scratch chain run match the ORM

Until now `alembic upgrade head` had never been run against an empty database
— production was built with Base.metadata.create_all() and then stamped, a
workaround scripts/init_db.py:12-14 documents explicitly. Once f9861a2caa12
was made idempotent the chain completes, and `alembic check` then surfaces the
handful of places where the schema it produces still disagrees with
src/data/models.py.

Every statement here is guarded, so this revision is a no-op against the
existing production database (which already matches the ORM) and only does
work on a fresh install.

Revision ID: 019_fresh_install_parity
Revises: 018_rule_backtest_gate
Create Date: 2026-08-02
"""
from alembic import op

revision = "019_fresh_install_parity"
down_revision = "018_rule_backtest_gate"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. sentinel_thresholds — dropped by f9861a2caa12 and never recreated by
    #    any migration, yet SentinelRepository reads it at :71 and upserts at
    #    :88, and the ORM still declares it. Production has it only because
    #    create_all() resurrected it. Built to the ORM's shape (models.py), not
    #    f9861's downgrade shape, which differs in several column types.
    #    f9861 把它 drop 掉後沒有任何 migration 重建，但 runtime 仍在讀寫，
    #    ORM 也還宣告著；production 有它是 create_all() 救回來的。
    op.execute("""
        CREATE TABLE IF NOT EXISTS sentinel_thresholds (
            id VARCHAR PRIMARY KEY,
            key VARCHAR NOT NULL UNIQUE,
            value NUMERIC(18, 8) NOT NULL,
            last_optimized_by VARCHAR,
            roi_hint TEXT,
            created_at TIMESTAMPTZ DEFAULT NOW(),
            updated_at TIMESTAMPTZ DEFAULT NOW()
        )
    """)

    # 2. reports.summary — present in the ORM, created by no migration.
    op.execute("ALTER TABLE reports ADD COLUMN IF NOT EXISTS summary TEXT")

    # 3. JSONB -> JSON. The baseline creates these three as JSONB
    #    (879480c2b31c:34-35, :81) but the ORM declares plain JSON, and
    #    f9861a2caa12 never normalized them — nobody noticed because
    #    production's copies came from create_all() and so were already JSON.
    #    The guard keeps this a genuine no-op there.
    #    baseline 建成 JSONB 但 ORM 宣告 JSON，f9861 從未收斂；production 沒事是
    #    因為它的欄位本來就是 create_all() 依 ORM 建的。
    for table, column in (
        ("users", "preferences"),
        ("users", "metadata"),
        ("settings", "value"),
    ):
        op.execute(f"""
            DO $$ BEGIN
              IF EXISTS (
                  SELECT 1 FROM information_schema.columns
                  WHERE table_name = '{table}'
                    AND column_name = '{column}'
                    AND data_type = 'jsonb'
              ) THEN
                ALTER TABLE {table} ALTER COLUMN "{column}" TYPE json
                    USING "{column}"::json;
              END IF;
            END $$;
        """)

    # 4. The baseline's UNIQUE(provider, identifier) on user_identities is not
    #    in the ORM. Identities are looked up by (provider, identifier) but the
    #    model has never declared the constraint, so autogenerate reports it as
    #    removed on every fresh install.
    op.execute(
        "ALTER TABLE user_identities "
        "DROP CONSTRAINT IF EXISTS user_identities_provider_identifier_key"
    )


def downgrade() -> None:
    # Only the additions are reversed. The JSONB->JSON coercions and the
    # dropped constraint are left alone: re-widening JSON to JSONB can fail on
    # rows written since, and restoring the unique constraint can fail on
    # duplicates. Neither is worth the downgrade risk.
    # 只回復新增的部分；型別回推與重建唯一約束都可能因既有資料而失敗。
    op.execute("ALTER TABLE reports DROP COLUMN IF EXISTS summary")
    op.execute("DROP TABLE IF EXISTS sentinel_thresholds")
