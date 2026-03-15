import sqlalchemy as sa

from .base import Base


class OAuthClient(Base):
    __tablename__ = "oauth_clients"

    client_id = sa.Column(sa.String(255), primary_key=True)
    data = sa.Column(sa.JSON, nullable=False)
    created_at = sa.Column(sa.DateTime, server_default=sa.func.now(), nullable=False)
