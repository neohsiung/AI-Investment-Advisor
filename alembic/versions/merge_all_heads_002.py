"""merge all heads 002

Revision ID: merge_all_heads_002
Revises: 004, efd641d67adb
Create Date: 2026-04-26 00:00:00.000000

"""
from typing import Sequence, Union

revision: str = 'merge_all_heads_002'
down_revision: Union[str, Sequence[str], None] = ('004', 'efd641d67adb')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
