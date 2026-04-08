"""invite_role

Revision ID: c1d2e3f4a5b6
Revises: b942da1196f0
Create Date: 2026-04-08 00:01:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c1d2e3f4a5b6"
down_revision: Union[str, None] = "b942da1196f0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "workspace_invites",
        sa.Column("role", sa.Text(), nullable=False, server_default="viewer"),
    )
    # Migrate existing workspace_members rows with role='member' to 'viewer'
    op.execute("UPDATE workspace_members SET role = 'viewer' WHERE role = 'member'")


def downgrade() -> None:
    op.execute("UPDATE workspace_members SET role = 'member' WHERE role = 'viewer'")
    op.drop_column("workspace_invites", "role")
