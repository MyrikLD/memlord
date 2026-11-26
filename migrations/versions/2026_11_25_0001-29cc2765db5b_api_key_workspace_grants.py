"""Add optional workspace grants to API keys."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "29cc2765db5b"
down_revision = "d4e5f6a1b2c3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("api_keys", sa.Column("workspace_grants", postgresql.JSONB(), nullable=True))


def downgrade() -> None:
    # The previous server treats every key as account-wide.
    scoped = op.get_bind().scalar(
        sa.text("SELECT EXISTS (SELECT 1 FROM api_keys WHERE workspace_grants IS NOT NULL)")
    )
    if scoped:
        raise RuntimeError("Revoke restricted API keys before downgrading.")
    op.drop_column("api_keys", "workspace_grants")
