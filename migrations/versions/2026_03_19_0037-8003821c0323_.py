"""Add personal workspaces; make memories.workspace_id NOT NULL

Revision ID: 8003821c0323
Revises: e5f6a1b2c3d4
Create Date: 2026-03-19 00:37:44.237421

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = '8003821c0323'
down_revision: Union[str, Sequence[str], None] = 'e5f6a1b2c3d4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Add is_personal column (nullable first so data migration can populate it)
    op.add_column(
        'workspaces',
        sa.Column('is_personal', sa.Boolean(), server_default='false', nullable=False),
    )

    # 2. Data migration: create a personal workspace for every existing user
    conn = op.get_bind()
    conn.execute(sa.text("""
        INSERT INTO workspaces (name, created_by, is_personal)
        SELECT '__personal_' || id || '__', id, TRUE
        FROM users
    """))

    # 3. Add each user as owner of their personal workspace
    conn.execute(sa.text("""
        INSERT INTO workspace_members (workspace_id, user_id, role)
        SELECT w.id, w.created_by, 'owner'
        FROM workspaces w
        WHERE w.is_personal = TRUE
    """))

    # 4. Backfill: assign NULL workspace_id memories to the user's personal workspace
    conn.execute(sa.text("""
        UPDATE memories m
        SET workspace_id = w.id
        FROM workspaces w
        WHERE w.created_by = m.created_by
          AND w.is_personal = TRUE
          AND m.workspace_id IS NULL
    """))

    # 5. Drop old unique constraint and FK (before changing nullability)
    op.drop_constraint('uq_memories_content_user', 'memories', type_='unique')
    op.drop_constraint(op.f('fk_memories_workspace_id_workspaces'), 'memories', type_='foreignkey')

    # 6. Set workspace_id NOT NULL and recreate FK with CASCADE
    op.alter_column('memories', 'workspace_id', existing_type=sa.INTEGER(), nullable=False)
    op.create_foreign_key(
        op.f('fk_memories_workspace_id_workspaces'),
        'memories', 'workspaces',
        ['workspace_id'], ['id'],
        ondelete='CASCADE',
    )

    # 7. Add new unique constraint: content unique per workspace
    op.create_unique_constraint(
        'uq_memories_content_workspace',
        'memories',
        ['content', 'workspace_id'],
    )

    # 8. Enforce one personal workspace per user
    op.create_index(
        'uq_workspaces_personal_per_user',
        'workspaces',
        ['created_by'],
        unique=True,
        postgresql_where=sa.text('is_personal = TRUE'),
    )


def downgrade() -> None:
    # 1. Drop new unique constraint and CASCADE FK
    op.drop_constraint('uq_memories_content_workspace', 'memories', type_='unique')
    op.drop_constraint(op.f('fk_memories_workspace_id_workspaces'), 'memories', type_='foreignkey')

    # 2. Make workspace_id nullable again and restore SET NULL FK
    op.alter_column('memories', 'workspace_id', existing_type=sa.INTEGER(), nullable=True)
    op.create_foreign_key(
        op.f('fk_memories_workspace_id_workspaces'),
        'memories', 'workspaces',
        ['workspace_id'], ['id'],
        ondelete='SET NULL',
    )

    # 3. Restore old unique constraint
    op.create_unique_constraint(
        'uq_memories_content_user',
        'memories',
        ['content', 'created_by'],
        postgresql_nulls_not_distinct=False,
    )

    # 4. Un-backfill: set workspace_id to NULL for memories in personal workspaces
    conn = op.get_bind()
    conn.execute(sa.text("""
        UPDATE memories m
        SET workspace_id = NULL
        FROM workspaces w
        WHERE w.id = m.workspace_id
          AND w.is_personal = TRUE
    """))

    # 5. Remove personal workspace members and workspaces
    conn.execute(sa.text("""
        DELETE FROM workspace_members wm
        USING workspaces w
        WHERE w.id = wm.workspace_id AND w.is_personal = TRUE
    """))
    conn.execute(sa.text("DELETE FROM workspaces WHERE is_personal = TRUE"))

    # 6. Drop partial unique index and is_personal column
    op.drop_index('uq_workspaces_personal_per_user', table_name='workspaces')
    op.drop_column('workspaces', 'is_personal')
