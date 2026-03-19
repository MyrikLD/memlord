"""Stage 2b: add UNIQUE constraint on workspaces.name

Revision ID: e5f6a1b2c3d4
Revises: d4e5f6a1b2c3
Create Date: 2026-03-18 00:03:00.000000
"""
from typing import Sequence, Union

from alembic import op

revision: str = "e5f6a1b2c3d4"
down_revision: Union[str, Sequence[str], None] = "d4e5f6a1b2c3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_unique_constraint("uq_workspaces_name", "workspaces", ["name"])


def downgrade() -> None:
    op.drop_constraint("uq_workspaces_name", "workspaces", type_="unique")