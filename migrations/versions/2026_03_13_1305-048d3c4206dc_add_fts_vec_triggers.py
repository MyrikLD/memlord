"""add_fts_vec_triggers

Revision ID: 048d3c4206dc
Revises: 7ce3668792b0
Create Date: 2026-03-13 12:50:23.745073

"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "048d3c4206dc"
down_revision: Union[str, Sequence[str], None] = "8f993ec86e3b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # FTS5 virtual table for BM25 full-text search
    op.execute(
        "CREATE VIRTUAL TABLE memories_fts "
        "USING fts5(content, memory_id UNINDEXED, tokenize='porter unicode61')"
    )

    # sqlite-vec virtual table for vector KNN search (384 dims, all-MiniLM-L6-v2)
    op.execute(
        "CREATE VIRTUAL TABLE memories_vec "
        "USING vec0(memory_id INTEGER PRIMARY KEY, embedding FLOAT[384])"
    )

    # Triggers to keep memories_fts in sync with memories
    op.execute(
        "CREATE TRIGGER memories_fts_ai AFTER INSERT ON memories BEGIN "
        "INSERT INTO memories_fts(memory_id, content) VALUES (new.id, new.content); "
        "END"
    )
    op.execute(
        "CREATE TRIGGER memories_fts_au AFTER UPDATE OF content ON memories BEGIN "
        "UPDATE memories_fts SET content = new.content WHERE memory_id = old.id; "
        "END"
    )
    op.execute(
        "CREATE TRIGGER memories_fts_ad AFTER DELETE ON memories BEGIN "
        "DELETE FROM memories_fts WHERE memory_id = old.id; "
        "END"
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("DROP TRIGGER IF EXISTS memories_fts_ad")
    op.execute("DROP TRIGGER IF EXISTS memories_fts_au")
    op.execute("DROP TRIGGER IF EXISTS memories_fts_ai")
    op.execute("DROP TABLE IF EXISTS memories_vec")
    op.execute("DROP TABLE IF EXISTS memories_fts")
