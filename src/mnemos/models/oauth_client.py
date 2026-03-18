import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from .base import Base


class OAuthClient(Base):
    __tablename__ = "oauth_clients"

    client_id = sa.Column(sa.String(255), primary_key=True)
    data = sa.Column(JSONB, nullable=False)
    user_id = sa.Column(sa.Integer, sa.ForeignKey("users.id"), nullable=True)
    created_at = sa.Column(sa.DateTime, server_default=sa.func.now(), nullable=False)
