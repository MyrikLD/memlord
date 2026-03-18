"""Stage 1: Users — add users table, link oauth_clients and memories to user

Revision ID: a1b2c3d4e5f6
Revises: 2a6c4515f145
Create Date: 2026-03-18 00:01:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, Sequence[str], None] = "2a6c4515f145"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Create users table
    op.create_table(
        "users",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("email", sa.Text, nullable=False),
        sa.Column("display_name", sa.Text, nullable=False, server_default=""),
        sa.Column("hashed_password", sa.Text, nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=False),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_unique_constraint("uq_users_email", "users", ["email"])

    # 2. Add user_id FK to oauth_clients (nullable — linked on first login)
    op.add_column(
        "oauth_clients",
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id"), nullable=True),
    )

    # 3. Add created_by to memories as nullable first (for backfill)
    op.add_column(
        "memories",
        sa.Column("created_by", sa.Integer, sa.ForeignKey("users.id"), nullable=True),
    )

    # 4. Backfill: if memories already exist, create a migration user and assign them
    conn = op.get_bind()
    count = conn.execute(sa.text("SELECT COUNT(*) FROM memories")).scalar()
    if count and count > 0:
        user_id = conn.execute(
            sa.text(
                "INSERT INTO users (email, display_name, hashed_password) "
                "VALUES ('migrated@mnemos.local', 'Migrated', 'no-password') "
                "RETURNING id"
            )
        ).scalar()
        conn.execute(
            sa.text("UPDATE memories SET created_by = :uid WHERE created_by IS NULL"),
            {"uid": user_id},
        )

    # 5. Set NOT NULL on created_by
    op.alter_column("memories", "created_by", nullable=False)

    # 6. Replace global content unique constraint with per-user unique constraint
    op.drop_constraint("uq_memories_content", "memories", type_="unique")
    op.create_unique_constraint(
        "uq_memories_content_user", "memories", ["content", "created_by"]
    )


def downgrade() -> None:
    op.drop_constraint("uq_memories_content_user", "memories", type_="unique")
    op.create_unique_constraint("uq_memories_content", "memories", ["content"])
    op.alter_column("memories", "created_by", nullable=True)
    op.drop_column("memories", "created_by")
    op.drop_column("oauth_clients", "user_id")
    op.drop_constraint("uq_users_email", "users", type_="unique")
    op.drop_table("users")