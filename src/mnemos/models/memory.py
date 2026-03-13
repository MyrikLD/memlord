import sqlalchemy as sa

from .base import Base


class Memory(Base):
    __tablename__ = "memories"

    id = sa.Column(sa.Integer, primary_key=True, autoincrement=True)
    content = sa.Column(sa.Text, unique=True, nullable=False)
    memory_type = sa.Column(sa.String(50), nullable=True)
    extra_data = sa.Column("metadata", sa.JSON, nullable=True)
    client_hostname = sa.Column(sa.String(255), nullable=True)
    created_at = sa.Column(sa.DateTime, server_default=sa.func.now(), nullable=False)
