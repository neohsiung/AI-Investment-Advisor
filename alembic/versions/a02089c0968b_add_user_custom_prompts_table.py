"""Add user_custom_prompts table

Revision ID: a02089c0968b
Revises: b7f2a91c3d0e
Create Date: 2026-04-10 08:37:55.442142

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a02089c0968b'
down_revision: Union[str, Sequence[str], None] = 'b7f2a91c3d0e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'user_custom_prompts',
        sa.Column('id', sa.String(), nullable=False, primary_key=True),
        sa.Column('user_id', sa.String(), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=True),
        sa.Column('agent_name', sa.String(), nullable=True),
        sa.Column('custom_prompt', sa.Text(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True)
    )
    op.create_index(op.f('ix_user_custom_prompts_agent_name'), 'user_custom_prompts', ['agent_name'], unique=False)
    op.create_index(op.f('ix_user_custom_prompts_user_id'), 'user_custom_prompts', ['user_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_user_custom_prompts_user_id'), table_name='user_custom_prompts')
    op.drop_index(op.f('ix_user_custom_prompts_agent_name'), table_name='user_custom_prompts')
    op.drop_table('user_custom_prompts')
