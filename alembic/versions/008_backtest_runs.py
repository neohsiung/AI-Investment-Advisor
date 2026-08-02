"""backtest_runs + backtest_equity_points: persist PortfolioBacktestEngine results

Enables a re-viewable backtest history (P4.1) — powers the backtest results
UI (P5.1) and lets strategy iterations be compared over time.

Revision ID: 008_backtest_runs
Revises: 007_decision_outcomes
Create Date: 2026-07-11
"""
from alembic import op
import sqlalchemy as sa

revision = "008_backtest_runs"
down_revision = "007_decision_outcomes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    is_sqlite = bind.dialect.name == "sqlite"
    ts_type = sa.DateTime(timezone=not is_sqlite)
    json_type = sa.JSON() if is_sqlite else sa.dialects.postgresql.JSONB()

    op.create_table(
        "backtest_runs",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("ticker", sa.String(), nullable=False),
        sa.Column("strategy_name", sa.String(), nullable=False),
        sa.Column("initial_cash", sa.Numeric(18, 4), nullable=False),
        sa.Column("final_cash", sa.Numeric(18, 4), nullable=False),
        sa.Column("metrics", json_type, nullable=False),
        sa.Column("trades", json_type, nullable=False),
        sa.Column("params", json_type, nullable=True),
        sa.Column("created_at", ts_type, nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    op.create_index("ix_backtest_runs_user_id", "backtest_runs", ["user_id"])
    op.create_index("ix_backtest_runs_ticker", "backtest_runs", ["ticker"])

    op.create_table(
        "backtest_equity_points",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("run_id", sa.String(), sa.ForeignKey("backtest_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("date", sa.String(), nullable=True),
        sa.Column("equity", sa.Numeric(18, 4), nullable=False),
    )
    op.create_index("ix_backtest_equity_points_run_id", "backtest_equity_points", ["run_id"])


def downgrade() -> None:
    op.drop_index("ix_backtest_equity_points_run_id", table_name="backtest_equity_points")
    op.drop_table("backtest_equity_points")
    op.drop_index("ix_backtest_runs_ticker", table_name="backtest_runs")
    op.drop_index("ix_backtest_runs_user_id", table_name="backtest_runs")
    op.drop_table("backtest_runs")
