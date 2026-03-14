from sqlalchemy import delete, insert, select, text, update
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

from mnemos.embeddings import embed
from mnemos.models import Memory, MemoryTag, Tag

_UNSET = object()


class MemoryDao:
    def __init__(self, s: AsyncSession) -> None:
        self._s = s

    async def _vec_insert(self, memory_id: int, content: str) -> None:
        vector = embed(content)
        vec_str = "[" + ",".join(str(v) for v in vector) + "]"
        await self._s.execute(
            text("INSERT INTO memories_vec(memory_id, embedding) VALUES (:id, :vec)"),
            {"id": memory_id, "vec": vec_str},
        )

    async def _vec_update(self, memory_id: int, content: str) -> None:
        vector = embed(content)
        vec_str = "[" + ",".join(str(v) for v in vector) + "]"
        await self._s.execute(
            text("UPDATE memories_vec SET embedding = :vec WHERE memory_id = :id"),
            {"vec": vec_str, "id": memory_id},
        )

    async def _vec_delete(self, memory_id: int) -> None:
        await self._s.execute(
            text("DELETE FROM memories_vec WHERE memory_id = :id"), {"id": memory_id}
        )

    async def _upsert_tags(self, memory_id: int, tags: list[str]) -> None:
        for tag_name in tags:
            normalized = tag_name.lower().strip()
            if not normalized:
                continue
            await self._s.execute(
                sqlite_insert(Tag).values(name=normalized).on_conflict_do_nothing()
            )
            tag_id = await self._s.scalar(select(Tag.id).where(Tag.name == normalized))
            await self._s.execute(
                sqlite_insert(MemoryTag)
                .values(memory_id=memory_id, tag_id=tag_id)
                .on_conflict_do_nothing()
            )

    async def _replace_tags(self, memory_id: int, tags: list[str]) -> None:
        await self._s.execute(delete(MemoryTag).where(MemoryTag.memory_id == memory_id))
        await self._upsert_tags(memory_id, tags)

    async def create(
        self,
        content: str,
        memory_type: str | None,
        metadata: dict | None,
        client_hostname: str | None,
        tags: list[str] | None,
    ) -> tuple[int, str, bool]:
        row = await self._s.execute(
            select(Memory.id, Memory.created_at).where(Memory.content == content)
        )
        existing = row.one_or_none()
        if existing is not None:
            memory_id, created_at = existing
            return memory_id, str(created_at), False

        memory_id, created_at = (
            await self._s.execute(
                insert(Memory)
                .values(
                    content=content,
                    memory_type=memory_type,
                    extra_data=metadata,
                    client_hostname=client_hostname,
                )
                .returning(Memory.id, Memory.created_at)
            )
        ).one()

        await self._vec_insert(memory_id, content)
        await self._upsert_tags(memory_id, tags or [])
        return memory_id, str(created_at), True

    async def update(
        self,
        id: int,
        content: str = _UNSET,  # type: ignore[assignment]
        memory_type: str | None = _UNSET,  # type: ignore[assignment]
        metadata: dict | None = _UNSET,  # type: ignore[assignment]
        tags: list[str] = _UNSET,  # type: ignore[assignment]
    ) -> tuple[int, str]:
        """Update memory fields. Pass _UNSET to leave a field unchanged; None sets it to NULL."""
        row = await self._s.execute(
            select(Memory.id, Memory.created_at).where(Memory.id == id)
        )
        existing = row.one_or_none()
        if existing is None:
            raise ValueError(f"Memory with id={id} not found")

        memory_id, created_at = existing

        values: dict = {}
        if content is not _UNSET:
            values["content"] = content
        if memory_type is not _UNSET:
            values["memory_type"] = memory_type
        if metadata is not _UNSET:
            values["extra_data"] = metadata

        if values:
            await self._s.execute(
                update(Memory).where(Memory.id == memory_id).values(**values)
            )

        if content is not _UNSET:
            await self._vec_update(memory_id, content)  # type: ignore[arg-type]

        if tags is not _UNSET:
            await self._replace_tags(memory_id, tags)  # type: ignore[arg-type]

        return memory_id, str(created_at)

    async def delete(self, id: int) -> None:
        await self._vec_delete(id)
        row = await self._s.execute(
            delete(Memory).where(Memory.id == id).returning(Memory.id)
        )
        if row.scalar_one_or_none() is None:
            raise ValueError(f"Memory with id={id} not found")

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
