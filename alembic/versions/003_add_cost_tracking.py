
"""Add request_costs and user_budget_tracking tables for cost analysis

Revision ID: 003_add_cost_tracking
Revises: 002_add_report_jobs
Create Date: 2026-04-27

"""
from alembic import op
import sqlalchemy as sa

revision = '003_add_cost_tracking'
down_revision = '002_add_report_jobs'
branch_labels = None
depends_on = None

def upgrade():
    # 1. 用戶預算表
    op.create_table(
        'user_budgets',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('user_id', sa.String(36), nullable=False, unique=True),
        sa.Column('monthly_budget_usd', sa.Float, default=129.0),
        sa.Column('weekly_budget_usd', sa.Float, default=32.25),
        sa.Column('current_week_spent_usd', sa.Float, default=0.0),
        sa.Column('current_month_spent_usd', sa.Float, default=0.0),
        sa.Column('tier_allocation', sa.JSON, default={
            'DeepResearch': 12.90,
            'MemoryDig': 11.29,
            'FastThink': 6.45,
            'Reflexive': 1.61
        }),
        sa.Column('budget_reset_day', sa.Integer, default=1),  # Day of month
        sa.Column('alert_threshold_pct', sa.Integer, default=85),
        sa.Column('hard_limit_enabled', sa.Boolean, default=True),
        sa.Column('created_at', sa.DateTime, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime, server_default=sa.func.now(), onupdate=sa.func.now()),
        sa.Index('idx_user_id', 'user_id')
    )
    
    # 2. 請求成本日誌表
    op.create_table(
        'request_costs',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('user_id', sa.String(36), nullable=False),
        sa.Column('request_id', sa.String(36), nullable=False),
        sa.Column('tier', sa.String(20), nullable=False),  # DeepResearch, MemoryDig, etc
        sa.Column('model_provider', sa.String(50), nullable=False),  # ollama, nvidia_nim, openrouter
        sa.Column('model_name', sa.String(100), nullable=False),  # claude-3.5-sonnet, etc
        sa.Column('fallback_used', sa.Boolean, default=False),
        sa.Column('fallback_priority', sa.Integer, nullable=True),
        sa.Column('input_tokens', sa.Integer, default=0),
        sa.Column('output_tokens', sa.Integer, default=0),
        sa.Column('cost_usd', sa.Float, default=0.0),
        sa.Column('success', sa.Boolean, default=True),
        sa.Column('latency_ms', sa.Integer, nullable=True),
        sa.Column('quality_score', sa.Float, nullable=True),
        sa.Column('created_at', sa.DateTime, server_default=sa.func.now()),
        sa.Index('idx_user_id', 'user_id'),
        sa.Index('idx_request_id', 'request_id'),
        sa.Index('idx_created_at', 'created_at'),
        sa.Index('idx_tier', 'tier'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'])
    )
    
    # 3. 周期性審查日誌
    op.create_table(
        'cost_review_logs',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('user_id', sa.String(36), nullable=False),
        sa.Column('review_week', sa.Integer, nullable=False),
        sa.Column('review_year', sa.Integer, nullable=False),
        sa.Column('total_requests', sa.Integer, default=0),
        sa.Column('total_cost_usd', sa.Float, default=0.0),
        sa.Column('cost_by_tier', sa.JSON),  # {DeepResearch: 8.5, MemoryDig: 12.3, ...}
        sa.Column('cost_by_provider', sa.JSON),  # {ollama: 0, nvidia_nim: 5.2, openrouter: 15.1}
        sa.Column('fallback_frequency_pct', sa.Float, default=0.0),
        sa.Column('success_rate_pct', sa.Float, default=100.0),
        sa.Column('avg_quality_score', sa.Float, default=8.0),
        sa.Column('recommendations', sa.JSON),  # {update_models: [...], optimize_tier: [...]}
        sa.Column('budget_status', sa.String(20), default='ok'),  # ok, warning, alert, critical
        sa.Column('reviewed_at', sa.DateTime, server_default=sa.func.now()),
        sa.Index('idx_user_id', 'user_id'),
        sa.Index('idx_review_week', 'review_week'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'])
    )
    
    # 4. 模型性能指標表
    op.create_table(
        'model_performance_metrics',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('model_provider', sa.String(50), nullable=False),
        sa.Column('model_name', sa.String(100), nullable=False),
        sa.Column('tier', sa.String(20), nullable=False),
        sa.Column('request_count', sa.Integer, default=0),
        sa.Column('success_count', sa.Integer, default=0),
        sa.Column('avg_latency_ms', sa.Float, default=0.0),
        sa.Column('avg_quality_score', sa.Float, default=0.0),
        sa.Column('cost_per_request_usd', sa.Float, default=0.0),
        sa.Column('last_updated', sa.DateTime, server_default=sa.func.now(), onupdate=sa.func.now()),
        sa.Index('idx_provider_model', 'model_provider', 'model_name'),
        sa.Index('idx_tier', 'tier')
    )

def downgrade():
    op.drop_table('model_performance_metrics')
    op.drop_table('cost_review_logs')
    op.drop_table('request_costs')
    op.drop_table('user_budgets')
