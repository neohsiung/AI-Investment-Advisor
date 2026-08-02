"""council_minutes.embedding vector(1536) -> vector(768)

Aligns the council-minute embedding column with the local nomic-embed-text
model (768 dims) used everywhere else in the stack, so semantic recall of
past council decisions actually works. All existing rows held a placeholder
[0.0]*1536 vector (semantic recall was never functional), so clearing them
loses nothing — they are re-embedded on next write.

Revision ID: 006_council_embedding_768
Revises: 005_add_event_queue
Create Date: 2026-07-11
"""
from alembic import op

# revision identifiers, used by Alembic.
revision = "006_council_embedding_768"
down_revision = "005_add_event_queue"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        return  # sqlite stores embedding as TEXT; nothing to do
    # Idempotent: only narrow if the column is still 1536 (the DDL may already
    # have been applied directly to a running prod DB). pgvector stores the
    # dimension directly in atttypmod.
    current = bind.exec_driver_sql(
        "SELECT atttypmod FROM pg_attribute "
        "WHERE attrelid='council_minutes'::regclass AND attname='embedding'"
    ).scalar()
    if current == 768:  # already vector(768)
        return
    # Existing values are all placeholder 1536-dim zero vectors and cannot cast
    # to 768; clear them, then narrow the column. Rows re-embed on next archive.
    op.execute("UPDATE council_minutes SET embedding = NULL")
    op.execute(
        "ALTER TABLE council_minutes "
        "ALTER COLUMN embedding TYPE vector(768) USING embedding::text::vector(768)"
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        return
    op.execute("UPDATE council_minutes SET embedding = NULL")
    op.execute(
        "ALTER TABLE council_minutes "
        "ALTER COLUMN embedding TYPE vector(1536) USING embedding::text::vector(1536)"
    )
