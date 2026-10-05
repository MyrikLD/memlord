"""memlord text search config (zhparser if available) + title-weighted search_vector

Revision ID: 5b7e9c1d2a3f
Revises: d4e5f6a1b2c3
Create Date: 2026-10-05 17:00:00.000000

Creates a text search configuration named 'memlord'. If the server ships the
zhparser extension it is used for Chinese word segmentation; otherwise the
config is a copy of 'simple' (previous behaviour). search_vector is rebuilt as
setweight(name, 'A') || setweight(content, 'B').
"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "5b7e9c1d2a3f"
down_revision: Union[str, Sequence[str], None] = "d4e5f6a1b2c3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_ENSURE_TS_CONFIG = """
DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_ts_config WHERE cfgname = 'memlord') THEN
    RETURN;
  END IF;
  IF EXISTS (SELECT 1 FROM pg_available_extensions WHERE name = 'zhparser') THEN
    BEGIN
      CREATE EXTENSION IF NOT EXISTS zhparser;
      CREATE TEXT SEARCH CONFIGURATION memlord (PARSER = zhparser);
      ALTER TEXT SEARCH CONFIGURATION memlord ADD MAPPING FOR n,v,a,i,e,l,j,t WITH simple;
      RETURN;
    EXCEPTION WHEN OTHERS THEN
      NULL;  -- zhparser not usable (e.g. missing privileges): fall back to simple
    END;
  END IF;
  CREATE TEXT SEARCH CONFIGURATION memlord (COPY = simple);
END $$;
"""

_WEIGHTED_EXPR = (
    "setweight(to_tsvector('memlord'::regconfig, name), 'A') || "
    "setweight(to_tsvector('memlord'::regconfig, content), 'B')"
)
_SIMPLE_EXPR = "to_tsvector('simple', content)"


def _rebuild_search_vector(expr: str) -> None:
    op.execute("DROP INDEX IF EXISTS ix_memories_search_vector")
    op.execute("ALTER TABLE memories DROP COLUMN IF EXISTS search_vector")
    op.execute(
        "ALTER TABLE memories ADD COLUMN search_vector tsvector "
        f"GENERATED ALWAYS AS ({expr}) STORED NOT NULL"
    )
    op.execute("CREATE INDEX ix_memories_search_vector ON memories USING gin (search_vector)")


def upgrade() -> None:
    op.execute(_ENSURE_TS_CONFIG)
    _rebuild_search_vector(_WEIGHTED_EXPR)


def downgrade() -> None:
    _rebuild_search_vector(_SIMPLE_EXPR)
    op.execute("DROP TEXT SEARCH CONFIGURATION IF EXISTS memlord")
