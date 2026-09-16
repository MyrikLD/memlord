"""add totp_secret

Revision ID: d4e5f6a1b2c3
Revises: 73136588cb14
Create Date: 2026-09-16 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "d4e5f6a1b2c3"
down_revision: Union[str, Sequence[str], None] = "73136588cb14"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("totp_secret", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "totp_secret")
