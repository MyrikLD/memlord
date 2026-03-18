from sqlalchemy import delete, insert, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from mnemos.embeddings import embed
from mnemos.models import Memory, MemoryTag, Tag
from mnemos.schemas import MemoryListItem, MemoryType

_UNSET = object()


def _embed_text(content: str, tags: list[str]) -> str:
    return f"{content} {' '.join(tags)}" if tags else content


class MemoryDao:
    def __init__(self, s: AsyncSession) -> None:
        self._s = s

    async def _upsert_tags(self, memory_id: int, tags: list[str]) -> None:
        for tag_name in tags:
            normalized = tag_name.lower().strip()
            if not normalized:
                continue
            await self._s.execute(
                pg_insert(Tag).values(name=normalized).on_conflict_do_nothing()
            )
            tag_id = await self._s.scalar(select(Tag.id).where(Tag.name == normalized))
            await self._s.execute(
                pg_insert(MemoryTag)
                .values(memory_id=memory_id, tag_id=tag_id)
                .on_conflict_do_nothing()
            )

    async def _fetch_tag_names(self, memory_id: int) -> list[str]:
        rows = await self._s.execute(
            select(Tag.name)
            .join(MemoryTag, MemoryTag.tag_id == Tag.id)
            .where(MemoryTag.memory_id == memory_id)
        )
        return [row[0] for row in rows.fetchall()]

    async def _cleanup_orphan_tags(self) -> None:
        await self._s.execute(delete(Tag).where(~Tag.id.in_(select(MemoryTag.tag_id))))

    async def _replace_tags(self, memory_id: int, tags: list[str]) -> None:
        await self._s.execute(delete(MemoryTag).where(MemoryTag.memory_id == memory_id))
        await self._upsert_tags(memory_id, tags)
        await self._cleanup_orphan_tags()

    async def create(
        self,
        content: str,
        memory_type: MemoryType,
        metadata: dict,
        tags: list[str],
        user_id: int,
    ) -> tuple[int, bool]:
        memory_id = await self._s.scalar(
            select(Memory.id).where(
                Memory.content == content, Memory.created_by == user_id
            )
        )
        if memory_id is not None:
            return memory_id, False

        memory_id = await self._s.scalar(
            insert(Memory)
            .values(
                content=str(content),
                memory_type=MemoryType(memory_type),
                extra_data=metadata or {},
                embedding=embed(_embed_text(content, tags or [])),
                created_by=user_id,
            )
            .returning(Memory.id)
        )
        assert memory_id is not None

        await self._upsert_tags(memory_id, tags or [])
        return memory_id, True

    async def update(
        self,
        id: int,
        user_id: int,
        content: str = _UNSET,  # type: ignore[assignment]
        memory_type: MemoryType = _UNSET,  # type: ignore[assignment]
        metadata: dict = _UNSET,  # type: ignore[assignment]
        tags: list[str] = _UNSET,  # type: ignore[assignment]
    ) -> int:
        """Update memory fields. Pass _UNSET to leave a field unchanged; None sets it to NULL."""
        memory_id = await self._s.scalar(
            select(Memory.id).where(Memory.id == id, Memory.created_by == user_id)
        )
        if memory_id is None:
            raise ValueError(f"Memory with id={id} not found")

        values: dict = {}
        if memory_type is not _UNSET:
            values["memory_type"] = MemoryType(memory_type)
        if metadata is not _UNSET:
            values["extra_data"] = metadata or {}

        if content is not _UNSET or tags is not _UNSET:
            new_content = (
                content
                if content is not _UNSET
                else (
                    await self._s.scalar(
                        select(Memory.content).where(Memory.id == memory_id)
                    )
                    or ""
                )
            )
            new_tags = (
                list(tags)
                if tags is not _UNSET
                else await self._fetch_tag_names(memory_id)
            )
            if content is not _UNSET:
                values["content"] = content
            values["embedding"] = embed(_embed_text(new_content, new_tags))

        if values:
            await self._s.execute(
                update(Memory).where(Memory.id == memory_id).values(**values)
            )

        if tags is not _UNSET:
            await self._replace_tags(memory_id, tags)  # type: ignore[arg-type]

        return memory_id

    async def delete(self, id: int, user_id: int) -> None:
        result = await self._s.scalar(
            delete(Memory)
            .where(Memory.id == id, Memory.created_by == user_id)
            .returning(Memory.id)
        )
        if result is None:
            raise ValueError(f"Memory with id={id} not found")
        await self._cleanup_orphan_tags()

    async def get(self, id: int, user_id: int) -> MemoryListItem | None:
        row = (
            (
                await self._s.execute(
                    select(
                        Memory.id,
                        Memory.content,
                        Memory.memory_type,
                        Memory.extra_data.label("metadata"),
                        Memory.created_at,
                    ).where(Memory.id == id, Memory.created_by == user_id)
                )
            )
            .mappings()
            .one_or_none()
        )
        if row is None:
            return None
        tags = (await self.fetch_tags([id])).get(id, [])
        return MemoryListItem(
            **row,
            tags=tags,
        )

    async def fetch_tags(self, memory_ids: list[int]) -> dict[int, list[str]]:
        rows = await self._s.execute(
            select(MemoryTag.memory_id, Tag.name)
            .join(Tag, MemoryTag.tag_id == Tag.id)
            .where(MemoryTag.memory_id.in_(memory_ids))
        )
        result: dict[int, list[str]] = {i: [] for i in memory_ids}
        for mid, name in rows.fetchall():
            result[mid].append(name)
        return result

    async def fetch_metadata(self, memory_ids: list[int]) -> dict[int, tuple]:
        rows = await self._s.execute(
            select(Memory.id, Memory.extra_data, Memory.created_at).where(
                Memory.id.in_(memory_ids)
            )
        )
        return {row.id: (row.extra_data, row.created_at) for row in rows.fetchall()}
