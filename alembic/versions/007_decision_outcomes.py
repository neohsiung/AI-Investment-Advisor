"""decision_outcomes: decision->outcome memory with alpha-anchored reflection

New table backing the P1 learning loop: every agent/CIO decision is recorded
as pending, then resolved after `horizon_days` with a realized return, a
benchmark return, alpha (realized - benchmark), and a short LLM-written
lesson that cites the alpha figure. This replaces self-graded reflection
(analyze_narrative_drift) with something falsifiable and backtestable.

Revision ID: 007_decision_outcomes
Revises: 006_council_embedding_768
Create Date: 2026-07-11
"""
from alembic import op
import sqlalchemy as sa

revision = "007_decision_outcomes"
down_revision = "006_council_embedding_768"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    is_sqlite = bind.dialect.name == "sqlite"
    pk_type = sa.String() if is_sqlite else sa.String()
    ts_type = sa.DateTime(timezone=not is_sqlite)

    op.create_table(
        "decision_outcomes",
        sa.Column("id", pk_type, primary_key=True),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("session_id", sa.String(), nullable=True),
        sa.Column("agent_name", sa.String(), nullable=False),
        sa.Column("ticker", sa.String(), nullable=False),
        sa.Column("signal", sa.String(), nullable=False),
        sa.Column("price_at_decision", sa.Numeric(18, 8), nullable=False),
        sa.Column("decided_at", ts_type, nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("horizon_days", sa.Integer(), nullable=False, server_default="5"),
        sa.Column("resolved_at", ts_type, nullable=True),
        sa.Column("realized_return_pct", sa.Numeric(10, 4), nullable=True),
        sa.Column("benchmark_return_pct", sa.Numeric(10, 4), nullable=True),
        sa.Column("alpha_pct", sa.Numeric(10, 4), nullable=True),
        sa.Column("lesson", sa.Text(), nullable=True),
        sa.Column("created_at", ts_type, nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    op.create_index("ix_decision_outcomes_user_id", "decision_outcomes", ["user_id"])
    op.create_index("ix_decision_outcomes_ticker", "decision_outcomes", ["ticker"])
    op.create_index(
        "ix_decision_outcomes_pending",
        "decision_outcomes",
        ["resolved_at", "decided_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_decision_outcomes_pending", table_name="decision_outcomes")
    op.drop_index("ix_decision_outcomes_ticker", table_name="decision_outcomes")
    op.drop_index("ix_decision_outcomes_user_id", table_name="decision_outcomes")
    op.drop_table("decision_outcomes")
