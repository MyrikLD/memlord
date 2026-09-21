"""workspace scoped tags

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a1b2c3
Create Date: 2026-09-18 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

from memlord.tags import normalize_tag


# revision identifiers, used by Alembic.
revision: str = 'e5f6a7b8c9d0'
down_revision: Union[str, Sequence[str], None] = 'd4e5f6a1b2c3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _link_count() -> int:
    return op.get_bind().execute(sa.text("SELECT count(*) FROM memory_tags")).scalar_one()


def _renormalize_names() -> int:
    """Bring pre-existing names (stored via lower/strip) to `normalize_tag`.

    Names that collapse onto an existing tag are merged into it. Returns the
    number of memory_tags rows dropped because a memory ended up linked to
    the same tag twice.
    """
    bind = op.get_bind()
    by_name = {
        name: tag_id
        for tag_id, name in bind.execute(sa.text("SELECT id, name FROM tags ORDER BY id")).all()
    }
    dropped = 0
    for name, tag_id in list(by_name.items()):
        new_name = normalize_tag(name)
        if new_name == name:
            continue
        if not new_name:
            new_name = name
        keep = by_name.get(new_name)
        if keep is None or keep == tag_id:
            bind.execute(
                sa.text("UPDATE tags SET name = :new WHERE id = :id"), {"new": new_name, "id": tag_id}
            )
            by_name[new_name] = tag_id
            continue
        dropped += bind.execute(
            sa.text(
                """
                DELETE FROM memory_tags mt
                WHERE mt.tag_id = :old
                  AND EXISTS (
                      SELECT 1 FROM memory_tags x
                      WHERE x.memory_id = mt.memory_id AND x.tag_id = :keep
                  )
                """
            ),
            {"old": tag_id, "keep": keep},
        ).rowcount
        bind.execute(
            sa.text("UPDATE memory_tags SET tag_id = :keep WHERE tag_id = :old"),
            {"old": tag_id, "keep": keep},
        )
        bind.execute(sa.text("DELETE FROM tags WHERE id = :id"), {"id": tag_id})
    return dropped


def upgrade() -> None:
    """Upgrade schema."""
    links_before = _link_count()
    links_before -= _renormalize_names()

    op.add_column('tags', sa.Column('workspace_id', sa.Integer(), nullable=True))
    op.add_column('tags', sa.Column('parent_id', sa.Integer(), nullable=True))
    op.drop_constraint(op.f('uq_tags_name'), 'tags', type_='unique')
    # Created before the data step so the split below is idempotent
    # (NULL workspace_id rows never collide with each other).
    op.create_unique_constraint(op.f('uq_tags_name_workspace_id'), 'tags', ['name', 'workspace_id'])

    # Split each global tag into one row per workspace that actually uses it,
    # repoint memory_tags at the per-workspace copy, then drop the global rows.
    # Every statement is a no-op on rerun.
    op.execute(
        """
        INSERT INTO tags (name, workspace_id)
        SELECT DISTINCT t.name, m.workspace_id
        FROM tags t
        JOIN memory_tags mt ON mt.tag_id = t.id
        JOIN memories m ON m.id = mt.memory_id
        WHERE t.workspace_id IS NULL
        ON CONFLICT (name, workspace_id) DO NOTHING
        """
    )
    op.execute(
        """
        UPDATE memory_tags mt
        SET tag_id = nt.id
        FROM tags ot, memories m, tags nt
        WHERE mt.tag_id = ot.id
          AND ot.workspace_id IS NULL
          AND m.id = mt.memory_id
          AND nt.name = ot.name
          AND nt.workspace_id = m.workspace_id
        """
    )
    op.execute("DELETE FROM tags WHERE workspace_id IS NULL")

    links_after = _link_count()
    if links_after != links_before:
        raise RuntimeError(
            f"memory_tags count changed during tag split: {links_before} -> {links_after}"
        )

    op.alter_column('tags', 'workspace_id', nullable=False)
    op.create_index(op.f('ix_tags_parent_id'), 'tags', ['parent_id'], unique=False)
    op.create_index(op.f('ix_tags_workspace_id'), 'tags', ['workspace_id'], unique=False)
    op.create_unique_constraint(op.f('uq_tags_id_workspace_id'), 'tags', ['id', 'workspace_id'])
    op.create_check_constraint('ck_tags_parent_id', 'tags', 'parent_id IS NULL OR parent_id != id')
    op.create_foreign_key(
        op.f('fk_tags_workspace_id_workspaces'),
        'tags',
        'workspaces',
        ['workspace_id'],
        ['id'],
        ondelete='CASCADE',
    )
    op.create_foreign_key(
        op.f('fk_tags_parent_id_tags'),
        'tags',
        'tags',
        ['parent_id', 'workspace_id'],
        ['id', 'workspace_id'],
        ondelete='SET NULL (parent_id)',
    )


def downgrade() -> None:
    """Downgrade schema."""
    links_before = _link_count()

    op.drop_constraint(op.f('fk_tags_parent_id_tags'), 'tags', type_='foreignkey')
    op.drop_constraint(op.f('fk_tags_workspace_id_workspaces'), 'tags', type_='foreignkey')
    op.drop_constraint('ck_tags_parent_id', 'tags', type_='check')
    op.drop_constraint(op.f('uq_tags_id_workspace_id'), 'tags', type_='unique')
    op.drop_index(op.f('ix_tags_workspace_id'), table_name='tags')
    op.drop_index(op.f('ix_tags_parent_id'), table_name='tags')

    # Collapse per-workspace copies back into one global tag per name
    # (the lowest id survives). A memory tagged with the same name through
    # two copies keeps a single link.
    op.execute(
        """
        DELETE FROM memory_tags mt
        USING tags t, (SELECT name, MIN(id) AS id FROM tags GROUP BY name) k
        WHERE mt.tag_id = t.id AND k.name = t.name AND t.id != k.id
          AND EXISTS (
              SELECT 1 FROM memory_tags x
              WHERE x.memory_id = mt.memory_id AND x.tag_id = k.id
          )
        """
    )
    op.execute(
        """
        UPDATE memory_tags mt
        SET tag_id = k.id
        FROM tags t, (SELECT name, MIN(id) AS id FROM tags GROUP BY name) k
        WHERE mt.tag_id = t.id AND k.name = t.name AND t.id != k.id
        """
    )
    op.execute(
        """
        DELETE FROM tags t
        USING (SELECT name, MIN(id) AS id FROM tags GROUP BY name) k
        WHERE k.name = t.name AND t.id != k.id
        """
    )

    op.drop_constraint(op.f('uq_tags_name_workspace_id'), 'tags', type_='unique')
    op.drop_column('tags', 'parent_id')
    op.drop_column('tags', 'workspace_id')
    op.create_unique_constraint(op.f('uq_tags_name'), 'tags', ['name'])

    links_after = _link_count()
    if links_after > links_before:
        raise RuntimeError(f"memory_tags grew during collapse: {links_before} -> {links_after}")
