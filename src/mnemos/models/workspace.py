import sqlalchemy as sa

from .base import Base


class Workspace(Base):
    __tablename__ = "workspaces"

    id = sa.Column(sa.Integer, primary_key=True, autoincrement=True)
    name = sa.Column(sa.Text, nullable=False, unique=True)
    created_by = sa.Column(sa.Integer, sa.ForeignKey("users.id"), nullable=False)
    created_at = sa.Column(
        sa.DateTime(timezone=False), server_default=sa.func.now(), nullable=False
    )
    is_personal = sa.Column(sa.Boolean, nullable=False, server_default="false")

    __table_args__ = (
        sa.Index(
            "uq_workspaces_personal_per_user",
            "created_by",
            unique=True,
            postgresql_where=sa.text("is_personal = TRUE"),
        ),
    )


class WorkspaceMember(Base):
    __tablename__ = "workspace_members"

    workspace_id = sa.Column(
        sa.Integer,
        sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
        primary_key=True,
        nullable=False,
    )
    user_id = sa.Column(
        sa.Integer,
        sa.ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
        nullable=False,
    )
    role = sa.Column(sa.Text, nullable=False, server_default="member")
    joined_at = sa.Column(
        sa.DateTime(timezone=False), server_default=sa.func.now(), nullable=False
    )


class WorkspaceInvite(Base):
    __tablename__ = "workspace_invites"

    id = sa.Column(sa.String(36), primary_key=True)  # UUID string
    workspace_id = sa.Column(
        sa.Integer,
        sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
    )
    created_by = sa.Column(sa.Integer, sa.ForeignKey("users.id"), nullable=False)
    expires_at = sa.Column(sa.DateTime(timezone=False), nullable=False)
    used_by = sa.Column(sa.Integer, sa.ForeignKey("users.id"), nullable=True)
    used_at = sa.Column(sa.DateTime(timezone=False), nullable=True)
