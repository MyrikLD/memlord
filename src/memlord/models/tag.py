import sqlalchemy as sa

from .base import Base


class Tag(Base):
    __tablename__ = "tags"

    id = sa.Column(sa.Integer, primary_key=True, autoincrement=True)
    name = sa.Column(sa.String(100), nullable=False)
    workspace_id = sa.Column(
        sa.Integer,
        sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    parent_id = sa.Column(sa.Integer, nullable=True, index=True)

    __table_args__ = (
        sa.UniqueConstraint("name", "workspace_id"),
        # Composite target for the self-FK below.
        sa.UniqueConstraint("id", "workspace_id"),
        # Keeps merges inside a single workspace.
        sa.ForeignKeyConstraint(
            ["parent_id", "workspace_id"],
            ["tags.id", "tags.workspace_id"],
            ondelete="SET NULL (parent_id)",
        ),
        sa.CheckConstraint("parent_id IS NULL OR parent_id != id", name="ck_tags_parent_id"),
    )
