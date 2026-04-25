"""merge heads

Revision ID: merge_heads_001
Revises: 0058ff181a57, e5f6a7b8c9d0
Create Date: 2026-04-19 08:15:00.000000

"""
from typing import Sequence, Union

# revision identifiers, used by Alembic.
revision: str = 'merge_heads_001'
down_revision: Union[str, Sequence[str], None] = ('0058ff181a57', 'e5f6a7b8c9d0')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
