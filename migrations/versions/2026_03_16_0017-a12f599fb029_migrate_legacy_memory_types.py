"""migrate legacy memory types

Revision ID: a12f599fb029
Revises: 7fbcd2675d42
Create Date: 2026-03-16 00:17:30.016256

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'a12f599fb029'
down_revision: Union[str, Sequence[str], None] = '7fbcd2675d42'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute(
        "UPDATE memories SET memory_type = 'fact' WHERE memory_type IN ('note', 'observation')"
    )
    op.execute(
        "UPDATE memories SET memory_type = 'instruction' WHERE memory_type IN ('task', 'plan')"
    )


def downgrade() -> None:
    """Downgrade schema."""
    pass
