import enum

import sqlalchemy as sa

from .base import Base


class TokenPurpose(str, enum.Enum):
    verify = "verify"
    reset = "reset"


class EmailToken(Base):
    __tablename__ = "email_tokens"
    __table_args__ = (sa.Index("ix_email_tokens_user_purpose", "user_id", "purpose"),)

    token_hash = sa.Column(sa.Text, primary_key=True)
    user_id = sa.Column(sa.Integer, nullable=False)
    purpose = sa.Column(
        sa.Enum(TokenPurpose, name="tokenpurpose", native_enum=False), nullable=False
    )
    expires_at = sa.Column(sa.DateTime(timezone=False), nullable=False, index=True)
