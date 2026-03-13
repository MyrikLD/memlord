import sqlalchemy as sa

from .base import Base


class MemoryTag(Base):
    __tablename__ = "memory_tags"

    memory_id = sa.Column(
        sa.Integer, sa.ForeignKey("memories.id", ondelete="CASCADE"), primary_key=True
    )
    tag_id = sa.Column(
        sa.Integer, sa.ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True
    )
