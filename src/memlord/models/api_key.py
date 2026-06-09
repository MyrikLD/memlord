import sqlalchemy as sa

from .base import Base


class ApiKey(Base):
    __tablename__ = "api_keys"

    id = sa.Column(sa.Integer, primary_key=True, autoincrement=True)
    user_id = sa.Column(
        sa.Integer, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name = sa.Column(sa.Text, nullable=False)
    token_hash = sa.Column(sa.Text, unique=True, nullable=False)
    prefix = sa.Column(sa.Text, nullable=False)
    created_at = sa.Column(
        sa.DateTime(timezone=False), server_default=sa.func.now(), nullable=False
    )
    last_used_at = sa.Column(sa.DateTime(timezone=False), nullable=True)

    __table_args__ = (sa.UniqueConstraint("user_id", "name"),)
