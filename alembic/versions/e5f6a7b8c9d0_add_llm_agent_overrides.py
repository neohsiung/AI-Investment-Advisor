"""add_llm_agent_overrides

Revision ID: e5f6a7b8c9d0
Revises: d3f8a1b2c4e5
Create Date: 2026-04-18 06:00:00.000000

Phase C (agent overrides):
Create `llm_agent_overrides` table with FK to llm_models and users,
following docs/architecture/multi_provider_multi_model_design.md §3.4.

Dialect notes:
  - JSONB is used on PostgreSQL; on SQLite (local dev) we degrade to JSON.
  - `TIMESTAMPTZ` is emulated by `sa.DateTime(timezone=True)`.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'e5f6a7b8c9d0'
down_revision: Union[str, Sequence[str], None] = 'd3f8a1b2c4e5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _json_type():
    """Return JSONB on PostgreSQL, JSON on other dialects (e.g. SQLite)."""
    return sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql")


def upgrade() -> None:
    """Create llm_agent_overrides table."""
    op.create_table(
        'llm_agent_overrides',
        sa.Column('id', sa.String(), nullable=False, primary_key=True),
        sa.Column(
            'user_id', sa.String(),
            sa.ForeignKey('users.id', ondelete='CASCADE'),
            nullable=False,
        ),
        sa.Column('agent_name', sa.String(100), nullable=False),
        sa.Column('override_tier', sa.String(20), nullable=True),
        sa.Column(
            'primary_model_id', sa.String(),
            sa.ForeignKey('llm_models.id', ondelete='RESTRICT'),
            nullable=True,
        ),
        sa.Column('fallback_model_ids', _json_type(), nullable=True, server_default=sa.text("'[]'")),
        sa.Column('forbid_local', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('forbid_fallback', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('enabled', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint('user_id', 'agent_name', name='uq_llm_agent_overrides_user_agent'),
        sa.CheckConstraint(
            "override_tier IN ('nano', 'fast', 'smart', 'advanced') OR override_tier IS NULL",
            name='chk_llm_agent_overrides_tier',
        ),
    )
    op.create_index(
        'ix_llm_agent_overrides_user_id',
        'llm_agent_overrides',
        ['user_id'],
        unique=False,
    )
    op.create_index(
        'ix_llm_agent_overrides_agent_name',
        'llm_agent_overrides',
        ['agent_name'],
        unique=False,
    )
    op.create_index(
        'ix_llm_agent_overrides_primary_model',
        'llm_agent_overrides',
        ['primary_model_id'],
        unique=False,
    )


def downgrade() -> None:
    """Drop llm_agent_overrides table."""
    op.drop_index('ix_llm_agent_overrides_primary_model', table_name='llm_agent_overrides')
    op.drop_index('ix_llm_agent_overrides_agent_name', table_name='llm_agent_overrides')
    op.drop_index('ix_llm_agent_overrides_user_id', table_name='llm_agent_overrides')
    op.drop_table('llm_agent_overrides')
