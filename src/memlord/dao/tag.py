import sqlalchemy as sa
from sqlalchemy import delete, func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from memlord.dao.workspace import WorkspaceDao
from memlord.filters import canonical_tag_id
from memlord.models import MemoryTag, Tag
from memlord.schemas.tag import (
    TagAlias,
    TagGroup,
)
from memlord.tags import normalize_tag


class TagDao:
    """Workspace tag dictionary: alias groups, merge/detach.

    Merges edit `tags.parent_id` only; `memory_tags` keeps the spelling each
    memory was stored with, so detaching an alias restores it exactly.
    """

    def __init__(self, s: AsyncSession, uid: int) -> None:
        self._s = s
        self._uid = uid
        self._ws_dao = WorkspaceDao(s, uid)

    async def _require_read(self, workspace_id: int) -> None:
        if not await self._ws_dao.can_read(workspace_id):
            raise PermissionError(f"No read access to workspace {workspace_id}")

    async def _require_write(self, workspace_id: int) -> None:
        if not await self._ws_dao.can_write(workspace_id):
            raise PermissionError(f"No write access to workspace {workspace_id}")

    # -- groups ------------------------------------------------------------

    def _groups_query(self, workspace_id: int, root_id: int | None = None):
        root = aliased(Tag)
        member = aliased(Tag)
        q = (
            select(
                root.id.label("id"),
                root.name.label("name"),
                func.array_agg(sa.distinct(member.name))
                .filter(member.id != root.id)
                .label("aliases"),
                func.count(sa.distinct(MemoryTag.memory_id)).label("memory_count"),
            )
            .select_from(root)
            .join(member, canonical_tag_id(member) == root.id)
            .outerjoin(MemoryTag, MemoryTag.tag_id == member.id)
            .where(root.workspace_id == workspace_id, root.parent_id.is_(None))
            .group_by(root.id, root.name)
        )
        if root_id is not None:
            q = q.where(root.id == root_id)
        return q

    @staticmethod
    def _to_group(row) -> TagGroup:
        return TagGroup(
            id=row["id"],
            name=row["name"],
            aliases=sorted(row["aliases"] or []),
            memory_count=row["memory_count"],
        )

    async def list_groups(self, workspace_id: int) -> list[TagGroup]:
        await self._require_read(workspace_id)
        q = self._groups_query(workspace_id).order_by("name")
        return [self._to_group(r) for r in (await self._s.execute(q)).mappings().all()]

    async def _group(self, root_id: int, workspace_id: int) -> TagGroup:
        q = self._groups_query(workspace_id, root_id)
        row = (await self._s.execute(q)).mappings().one_or_none()
        if row is None:
            raise ValueError("Tag not found")
        return self._to_group(row)

    async def _tag(self, workspace_id: int, name: str):
        """Tag row (id, name, parent_id) by name."""
        normalized = normalize_tag(name)
        tag = (
            (
                await self._s.execute(
                    select(Tag.id, Tag.name, Tag.parent_id).where(
                        Tag.workspace_id == workspace_id, Tag.name == normalized
                    )
                )
            )
            .mappings()
            .one_or_none()
        )
        if tag is None:
            raise ValueError(f"Tag {normalized!r} not found")
        return tag

    async def _resolve_root(self, workspace_id: int, name: str):
        """Canonical tag row of `name`'s group."""
        tag = await self._tag(workspace_id, name)
        if tag["parent_id"] is None:
            return tag
        root = (
            (
                await self._s.execute(
                    select(Tag.id, Tag.name, Tag.parent_id).where(Tag.id == tag["parent_id"])
                )
            )
            .mappings()
            .one()
        )
        return root

    # -- merge / detach ------------------------------------------------------

    async def merge(self, workspace_id: int, source: str, target: str) -> TagGroup:
        """Make `source` an alias of `target`'s canonical tag.

        A canonical `source` brings its aliases along; an alias `source` moves
        alone, leaving the rest of its old group in place.
        """
        await self._require_write(workspace_id)
        src = await self._tag(workspace_id, source)
        dst = await self._resolve_root(workspace_id, target)
        if src["id"] == dst["id"] or (src["parent_id"] == dst["id"]):
            raise ValueError(f"{source!r} and {target!r} are already in the same group")
        moved = Tag.id == src["id"]
        if src["parent_id"] is None:
            moved = sa.or_(moved, Tag.parent_id == src["id"])
        await self._s.execute(
            update(Tag).where(Tag.workspace_id == workspace_id, moved).values(parent_id=dst["id"])
        )
        return await self._group(dst["id"], workspace_id)

    async def detach(self, workspace_id: int, alias: str) -> TagGroup:
        """Undo a merge for one alias: it becomes a canonical tag again."""
        await self._require_write(workspace_id)
        row = await self._tag(workspace_id, alias)
        if row["parent_id"] is None:
            raise ValueError(f"Tag {row['name']!r} is not an alias")
        await self._s.execute(update(Tag).where(Tag.id == row["id"]).values(parent_id=None))
        # The detached tag, or the group it left, may now carry nothing.
        await self.cleanup_orphans()
        try:
            return await self._group(row["id"], workspace_id)
        except ValueError:
            return TagGroup(id=row["id"], name=row["name"], memory_count=0)

    # -- export / import -----------------------------------------------------

    async def aliases(self, workspace_id: int) -> list[TagAlias]:
        await self._require_read(workspace_id)
        root = aliased(Tag)
        rows = await self._s.execute(
            select(Tag.name, root.name.label("canonical"))
            .join(root, root.id == Tag.parent_id)
            .where(Tag.workspace_id == workspace_id)
            .order_by(root.name, Tag.name)
        )
        return [TagAlias(alias=r[0], canonical=r[1]) for r in rows.fetchall()]

    async def ensure_alias(self, workspace_id: int, alias: str, canonical: str) -> bool:
        """Recreate an exported alias edge. Returns True if a merge was applied."""
        await self._require_write(workspace_id)
        names = {normalize_tag(alias), normalize_tag(canonical)}
        names.discard("")
        if len(names) != 2:
            return False
        for name in names:
            await self._s.execute(
                pg_insert(Tag).values(name=name, workspace_id=workspace_id).on_conflict_do_nothing()
            )
        src = await self._resolve_root(workspace_id, alias)
        dst = await self._resolve_root(workspace_id, canonical)
        if src["id"] == dst["id"]:
            return False
        await self.merge(workspace_id, alias, canonical)
        return True

    # -- housekeeping --------------------------------------------------------

    async def cleanup_orphans(self) -> None:
        """Drop tags that carry no memories and take no part in any alias group."""
        child = aliased(Tag)
        await self._s.execute(
            delete(Tag).where(
                Tag.parent_id.is_(None),
                ~Tag.id.in_(select(MemoryTag.tag_id)),
                ~Tag.id.in_(select(child.parent_id).where(child.parent_id.isnot(None))),
            )
        )
