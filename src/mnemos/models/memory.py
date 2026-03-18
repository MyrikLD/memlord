import sqlalchemy as sa
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR

from .base import Base


class Memory(Base):
    __tablename__ = "memories"

    id = sa.Column(sa.Integer, primary_key=True, autoincrement=True)
    content = sa.Column(sa.Text, nullable=False)
    created_by = sa.Column(sa.Integer, sa.ForeignKey("users.id"), nullable=False)
    memory_type = sa.Column(sa.String(50), nullable=False)
    extra_data = sa.Column("metadata", JSONB, nullable=False, server_default="{}")
    created_at = sa.Column(
        sa.DateTime(timezone=False), server_default=sa.func.now(), nullable=False
    )
    embedding = sa.Column(Vector(384), nullable=True)
    search_vector = sa.Column(
        TSVECTOR,
        sa.Computed("to_tsvector('simple', content)", persisted=True),
        nullable=False,
    )

    __table_args__ = (
        sa.UniqueConstraint("content", "created_by", name="uq_memories_content_user"),
        sa.Index("ix_memories_search_vector", "search_vector", postgresql_using="gin"),
        sa.Index(
            "ix_memories_embedding",
            "embedding",
            postgresql_using="hnsw",
            postgresql_with={"m": 16, "ef_construction": 64},
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )
