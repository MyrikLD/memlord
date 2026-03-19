import sqlalchemy as sa

from .base import Base


class SchemaVersion(Base):
    __tablename__ = "schema_version"

    version = sa.Column(sa.Integer, primary_key=True)
    applied_at = sa.Column(sa.DateTime, server_default=sa.func.now(), nullable=False)
