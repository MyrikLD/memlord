import sqlalchemy as sa

from .base import Base


class Tag(Base):
    __tablename__ = "tags"

    id = sa.Column(sa.Integer, primary_key=True, autoincrement=True)
    name = sa.Column(sa.String(100), unique=True, nullable=False)
