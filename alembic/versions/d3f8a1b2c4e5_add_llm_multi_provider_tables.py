"""add_llm_multi_provider_tables

Revision ID: d3f8a1b2c4e5
Revises: a02089c0968b
Create Date: 2026-04-18 04:40:00.000000

Phase A (multi-provider multi-model):
Create three independent tables (Provider / Model / Tier Binding) with
foreign keys ON DELETE RESTRICT, following
`docs/architecture/multi_provider_multi_model_design.md` §3.

The fourth table `llm_agent_overrides` is intentionally deferred to Phase C.

Dialect notes:
  - JSONB is used on PostgreSQL; on SQLite (local dev) we degrade to JSON.
  - `TIMESTAMPTZ` is emulated by `sa.DateTime(timezone=True)` (SQLite ignores tz).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'd3f8a1b2c4e5'
down_revision: Union[str, Sequence[str], None] = '0058ff181a57'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _json_type():
    """Return JSONB on PostgreSQL, JSON on other dialects (e.g. SQLite)."""
    # NOTE: with_variant lets SQLAlchemy pick JSONB for postgresql dialect
    # while falling back to plain JSON on sqlite for local macOS dev.
    return sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql")


def upgrade() -> None:
    """Create llm_providers, llm_models, llm_tier_bindings tables."""
    # ── llm_providers ────────────────────────────────────────────────────
    op.create_table(
        'llm_providers',
        sa.Column('id', sa.String(), nullable=False, primary_key=True),
        sa.Column('user_id', sa.String(), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('provider_code', sa.String(), nullable=False),
        sa.Column('display_name', sa.String(), nullable=False),
        sa.Column('base_url', sa.Text(), nullable=True),
        sa.Column('encrypted_api_key', sa.Text(), nullable=True),
        sa.Column('enabled', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('extra_config', _json_type(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column('health_status', sa.String(), nullable=True),
        sa.Column('health_detail', _json_type(), nullable=True),
        sa.Column('last_checked_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint('user_id', 'provider_code', 'display_name', name='uq_llm_providers_user_code_name'),
    )
    op.create_index('ix_llm_providers_user_enabled', 'llm_providers', ['user_id', 'enabled'], unique=False)
    op.create_index('ix_llm_providers_provider_code', 'llm_providers', ['provider_code'], unique=False)

    # ── llm_models ───────────────────────────────────────────────────────
    op.create_table(
        'llm_models',
        sa.Column('id', sa.String(), nullable=False, primary_key=True),
        sa.Column(
            'provider_id', sa.String(),
            sa.ForeignKey('llm_providers.id', ondelete='RESTRICT'),
            nullable=False,
        ),
        sa.Column('model_code', sa.String(), nullable=False),
        sa.Column('display_name', sa.String(), nullable=False),
        sa.Column('capability_tool_calling', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('capability_vision', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('capability_json_mode', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('capability_streaming', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('capability_embeddings', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('context_window', sa.Integer(), nullable=True),
        sa.Column('input_cost_per_1k', sa.Numeric(12, 6), nullable=True),
        sa.Column('output_cost_per_1k', sa.Numeric(12, 6), nullable=True),
        sa.Column('source', sa.String(), nullable=False, server_default=sa.text("'manual'")),
        sa.Column('raw_discovery', _json_type(), nullable=True),
        sa.Column('enabled', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint('provider_id', 'model_code', name='uq_llm_models_provider_code'),
        sa.CheckConstraint(
            "source IN ('manual', 'auto_discovered', 'seed')",
            name='chk_llm_models_source',
        ),
    )
    op.create_index('ix_llm_models_provider_enabled', 'llm_models', ['provider_id', 'enabled'], unique=False)
    op.create_index('ix_llm_models_enabled', 'llm_models', ['enabled'], unique=False)

    # ── llm_tier_bindings ────────────────────────────────────────────────
    op.create_table(
        'llm_tier_bindings',
        sa.Column('id', sa.String(), nullable=False, primary_key=True),
        sa.Column('user_id', sa.String(), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('tier', sa.String(), nullable=False),
        sa.Column(
            'primary_model_id', sa.String(),
            sa.ForeignKey('llm_models.id', ondelete='RESTRICT'),
            nullable=False,
        ),
        # fallback_model_ids is a JSONB/JSON array of model UUIDs (logical FK, validated
        # at application layer — PG can't set FK on JSONB array elements).
        sa.Column('fallback_model_ids', _json_type(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column('per_candidate_config', _json_type(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column('budget_aware', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint('user_id', 'tier', name='uq_llm_tier_bindings_user_tier'),
        sa.CheckConstraint(
            "tier IN ('nano', 'fast', 'smart', 'advanced')",
            name='chk_llm_tier_bindings_tier',
        ),
    )
    op.create_index('ix_llm_tier_bindings_primary_model', 'llm_tier_bindings', ['primary_model_id'], unique=False)


def downgrade() -> None:
    """Reverse-drop order: tier_bindings → models → providers."""
    op.drop_index('ix_llm_tier_bindings_primary_model', table_name='llm_tier_bindings')
    op.drop_table('llm_tier_bindings')

    op.drop_index('ix_llm_models_enabled', table_name='llm_models')
    op.drop_index('ix_llm_models_provider_enabled', table_name='llm_models')
    op.drop_table('llm_models')

    op.drop_index('ix_llm_providers_provider_code', table_name='llm_providers')
    op.drop_index('ix_llm_providers_user_enabled', table_name='llm_providers')
    op.drop_table('llm_providers')
