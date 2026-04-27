from datetime import datetime
from typing import Any

import sqlalchemy as sa
from pgvector.sqlalchemy import Vector
from sqlalchemy import Float, bindparam, delete, insert, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from memlord.config import settings
from memlord.dao.workspace import WorkspaceDao
from memlord.embeddings import embed
from memlord.models import Memory, MemoryTag, Tag
from memlord.schemas import MemoryListItem, MemoryType

_UNSET: Any = object()


def _embed_text(content: str, tags: set[str]) -> str:
    return f"{content} {' '.join(sorted(tags))}" if tags else content


class MemoryDao:
    def __init__(self, s: AsyncSession, uid: int) -> None:
        self._s = s
        self._uid = uid
        self._ws_dao = WorkspaceDao(s, uid)

    async def _upsert_tags(self, memory_id: int, tags: set[str]) -> None:
        for tag_name in tags:
            normalized = tag_name.lower().strip()
            if not normalized:
                continue
            await self._s.execute(pg_insert(Tag).values(name=normalized).on_conflict_do_nothing())
            tag_id = await self._s.scalar(select(Tag.id).where(Tag.name == normalized))
            await self._s.execute(
                pg_insert(MemoryTag)
                .values(memory_id=memory_id, tag_id=tag_id)
                .on_conflict_do_nothing()
            )

    async def _fetch_tag_names(self, memory_id: int) -> set[str]:
        rows = await self._s.execute(
            select(Tag.name)
            .join(MemoryTag, MemoryTag.tag_id == Tag.id)
            .where(MemoryTag.memory_id == memory_id)
        )
        return {row[0] for row in rows.fetchall()}

    async def _cleanup_orphan_tags(self) -> None:
        await self._s.execute(delete(Tag).where(~Tag.id.in_(select(MemoryTag.tag_id))))

    async def _replace_tags(self, memory_id: int, tags: set[str]) -> None:
        await self._s.execute(delete(MemoryTag).where(MemoryTag.memory_id == memory_id))
        await self._upsert_tags(memory_id, tags)
        await self._cleanup_orphan_tags()

    async def _check_near_duplicate(self, vector: list[float], workspace_id: int) -> None:
        """Raise ValueError if a near-duplicate exists in the workspace."""
        vec_param = bindparam("vec", type_=Vector(384))
        distance_expr = Memory.embedding.op("<=>", return_type=Float)(vec_param)
        dup_row = (
            (
                await self._s.execute(
                    select(Memory.id, distance_expr.label("distance"))
                    .where(
                        Memory.embedding.isnot(None),
                        Memory.workspace_id == workspace_id,
                    )
                    .order_by(distance_expr)
                    .limit(1),
                    {"vec": vector},
                )
            )
            .mappings()
            .one_or_none()
        )
        if dup_row is None:
            return
        similarity = 1.0 - dup_row["distance"]
        if similarity >= settings.dedup_threshold:
            raise ValueError(
                f"Near-duplicate found (id={dup_row['id']}, similarity={round(similarity, 4):.4f}). "
                f"Review with get_memory({dup_row['id']}). Pass force=True to store anyway."
            )

    async def get_id_by_name(self, name: str, workspace_id: int | None = None) -> int | None:
        if workspace_id is None:
            workspace_id = await self._personal_workspace_id()
        return await self._s.scalar(
            select(Memory.id).where(
                Memory.name == name,
                Memory.workspace_id == workspace_id,
            )
        )

    async def _personal_workspace_id(self) -> int:
        return (await self._ws_dao.get_personal()).id

    async def _accessible_workspace_ids(self, write: bool = False) -> list[int]:
        return await self._ws_dao.get_accessible_workspace_ids(write=write)

    async def create(
        self,
        content: str,
        memory_type: MemoryType,
        metadata: dict,
        tags: set[str],
        name: str,
        workspace_id: int | None = None,
        force: bool = False,
    ) -> tuple[int, bool]:
        if workspace_id is None:
            workspace_id = await self._personal_workspace_id()
        else:
            if not await self._ws_dao.can_write(workspace_id):
                raise ValueError(f"No write access to workspace {workspace_id!r}")

        memory_id = await self._s.scalar(
            select(Memory.id).where(
                Memory.content == content,
                Memory.workspace_id == workspace_id,
            )
        )
        if memory_id is not None:
            return memory_id, False

        vector = await embed(_embed_text(content, tags or set()))

        if not force:
            await self._check_near_duplicate(vector, workspace_id)

        memory_id = await self._s.scalar(
            insert(Memory)
            .values(
                content=str(content),
                memory_type=MemoryType(memory_type),
                extra_data=metadata or {},
                embedding=vector,
                created_by=self._uid,
                workspace_id=workspace_id,
                name=name,
            )
            .returning(Memory.id)
        )
        assert memory_id is not None

        await self._upsert_tags(memory_id, tags or set())
        return memory_id, True

    async def update(
        self,
        id: int,
        workspace_id: int | None = None,
        content: str = _UNSET,  # type: ignore[assignment]
        memory_type: MemoryType = _UNSET,  # type: ignore[assignment]
        metadata: dict = _UNSET,  # type: ignore[assignment]
        tags: set[str] = _UNSET,  # type: ignore[assignment]
        name: str | None = _UNSET,  # type: ignore[assignment]
    ) -> tuple[int, str]:
        """Update memory fields. Pass _UNSET to leave a field unchanged."""
        if workspace_id is None:
            workspace_id = await self._personal_workspace_id()
        else:
            if not await self._ws_dao.can_write(workspace_id):
                raise ValueError(f"No write access to workspace {workspace_id!r}")

        memory_id = await self._s.scalar(
            select(Memory.id).where(Memory.id == id, Memory.workspace_id == workspace_id)
        )
        if memory_id is None:
            raise ValueError(f"Memory with id={id} not found")

        values: dict = {}
        if memory_type is not _UNSET:
            values["memory_type"] = MemoryType(memory_type)
        if metadata is not _UNSET:
            values["extra_data"] = metadata or {}
        if name is not _UNSET:
            values["name"] = name

        if content is not _UNSET or tags is not _UNSET:
            new_content = (
                content
                if content is not _UNSET
                else (
                    await self._s.scalar(select(Memory.content).where(Memory.id == memory_id)) or ""
                )
            )
            new_tags = set(tags) if tags is not _UNSET else await self._fetch_tag_names(memory_id)
            if content is not _UNSET:
                values["content"] = content
            values["embedding"] = await embed(_embed_text(new_content, new_tags))

        if values:
            final_name: str = await self._s.scalar(  # type: ignore[assignment]
                update(Memory).where(Memory.id == memory_id).values(**values).returning(Memory.name)
            )
        else:
            final_name = await self._s.scalar(  # type: ignore[assignment]
                select(Memory.name).where(Memory.id == memory_id)
            )

        if tags is not _UNSET:
            await self._replace_tags(memory_id, tags)

        return memory_id, final_name

    async def delete(self, id: int, workspace_id: int | None = None) -> None:
        if workspace_id is None:
            workspace_id = await self._personal_workspace_id()
        else:
            if not await self._ws_dao.can_write(workspace_id):
                raise ValueError(f"No write access to workspace {workspace_id!r}")

        result = await self._s.scalar(
            delete(Memory)
            .where(
                Memory.id == id,
                Memory.workspace_id == workspace_id,
            )
            .returning(Memory.id)
        )
        if result is None:
            raise ValueError(f"Memory with id={id} not found")
        await self._cleanup_orphan_tags()

    async def get(
        self,
        *,
        id: int | None = None,
        name: str | None = None,
        workspace_id: int | None = None,
    ) -> MemoryListItem | None:
        if id is None and name is None:
            raise ValueError("Either id or name must be provided")
        if workspace_id is None:
            workspace_id = await self._personal_workspace_id()
        elif not await self._ws_dao.can_read(workspace_id):
            raise ValueError(f"No read access to workspace {workspace_id}")

        q = select(
            Memory.id,
            Memory.name,
            Memory.content,
            Memory.memory_type,
            Memory.extra_data.label("metadata"),
            Memory.created_at,
            Memory.workspace_id,
        ).where(Memory.workspace_id == workspace_id)
        if id is not None:
            q = q.where(Memory.id == id)
        if name is not None:
            q = q.where(Memory.name == name)

        row = (await self._s.execute(q)).mappings().one_or_none()
        if row is None:
            return None
        memory_id: int = row["id"]
        tags = (await self.fetch_tags([memory_id])).get(memory_id, set())
        return MemoryListItem(**row, tags=tags)

    async def move(self, id: int, from_workspace_id: int, to_workspace_id: int) -> None:
        """Move memory to a different workspace. Raises ValueError if not found or duplicate."""
        workspace_ids = await self._accessible_workspace_ids(write=True)
        if to_workspace_id not in workspace_ids:
            raise PermissionError(f"No access to workspace {to_workspace_id}")
        if from_workspace_id not in workspace_ids:
            raise PermissionError(f"No access to workspace {from_workspace_id}")

        q = select(Memory.id, Memory.name, Memory.content).where(
            Memory.id == id, Memory.workspace_id == from_workspace_id
        )

        row = (await self._s.execute(q)).mappings().one_or_none()
        if row is None:
            raise ValueError(f"Memory with id={id} not found")

        duplicate = await self._s.scalar(
            select(Memory.id).where(
                sa.or_(
                    Memory.content == row["content"],
                    Memory.name == row["name"],
                ),
                Memory.workspace_id == to_workspace_id,
                Memory.id != id,
            )
        )
        if duplicate is not None:
            raise ValueError(
                "A memory with the same content or name already exists in the target workspace"
            )

        await self._s.execute(
            update(Memory).where(Memory.id == id).values(workspace_id=to_workspace_id)
        )

    async def fetch_tags(self, memory_ids: list[int]) -> dict[int, set[str]]:
        rows = await self._s.execute(
            select(MemoryTag.memory_id, Tag.name)
            .join(Tag, MemoryTag.tag_id == Tag.id)
            .where(MemoryTag.memory_id.in_(memory_ids))
        )
        result = {i: set() for i in memory_ids}
        for mid, name in rows.fetchall():
            result[mid].add(name)
        return result

    async def fetch_metadata(self, memory_ids: list[int]) -> dict[int, tuple[dict, datetime]]:
        rows = await self._s.execute(
            select(
                Memory.id,
                Memory.extra_data,
                Memory.created_at,
            ).where(Memory.id.in_(memory_ids))
        )
        return {row.id: (row.extra_data, row.created_at) for row in rows.fetchall()}
