"""risk_keywords: add UNIQUE constraint on keyword

Root cause fix (2026-07-12): RiskKeywordRepository.seed_defaults() and
add_if_not_exists() both use `INSERT ... ON CONFLICT (keyword) DO NOTHING`,
but the table only ever had a PK on `id` — no unique constraint on `keyword`.
Every seed/discovery insert silently failed with
psycopg2.errors.InvalidColumnReference, so risk_keywords stayed empty in
production and the entire weighted breaking-news detection dimension never
fired (score_text() always summed to 0 against an empty active-keyword set).

Revision ID: 009_risk_keywords_unique
Revises: 008_backtest_runs
Create Date: 2026-07-12
"""
from alembic import op

revision = "009_risk_keywords_unique"
down_revision = "008_backtest_runs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        return  # sqlite doesn't enforce this the same way; ON CONFLICT works via rowid uniqueness
    op.create_unique_constraint("uq_risk_keywords_keyword", "risk_keywords", ["keyword"])


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        return
    op.drop_constraint("uq_risk_keywords_keyword", "risk_keywords", type_="unique")
