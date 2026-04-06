"""add workspace description

Revision ID: ffd5e65054bc
Revises: 8f44baaf5579
Create Date: 2026-03-19 17:54:13.555231

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "ffd5e65054bc"
down_revision: Union[str, Sequence[str], None] = "8f44baaf5579"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("workspaces", sa.Column("description", sa.Text, nullable=True))


def downgrade() -> None:
    op.drop_column("workspaces", "description")
