from fastmcp import FastMCP
from mcp.types import ToolAnnotations
from mnemos.db import MCPSessionDep
from mnemos.models import Memory, MemoryTag, Tag
from mnemos.schemas import MemoryResult
from mnemos.search import hybrid_search
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

mcp = FastMCP()


async def _fetch_tags(s: AsyncSession, memory_ids: list[int]) -> dict[int, list[str]]:
    rows = await s.execute(
        select(MemoryTag.memory_id, Tag.name)
        .join(Tag, MemoryTag.tag_id == Tag.id)
        .where(MemoryTag.memory_id.in_(memory_ids))
    )
    result: dict[int, list[str]] = {i: [] for i in memory_ids}
    for mid, name in rows.fetchall():
        result[mid].append(name)
    return result


async def _fetch_metadata(s: AsyncSession, memory_ids: list[int]) -> dict[int, tuple]:
    rows = await s.execute(
        select(Memory.id, Memory.extra_data, Memory.created_at).where(
            Memory.id.in_(memory_ids)
        )
    )
    return {row.id: (row.extra_data, row.created_at) for row in rows.fetchall()}


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False))
async def retrieve_memory(
    query: str,
    limit: int = 10,
    similarity_threshold: float = 0.7,
    s: AsyncSession = MCPSessionDep,  # type: ignore[assignment]
) -> list[MemoryResult]:
    """Hybrid semantic + full-text search over stored memories."""
    results = await hybrid_search(
        s,
        query=query,
        limit=limit,
        similarity_threshold=similarity_threshold,
    )

    if not results:
        return []

    ids = [r.id for r in results]
    tags_map = await _fetch_tags(s, ids)
    meta_map = await _fetch_metadata(s, ids)

    output = []
    for r in results:
        metadata, created_at = meta_map.get(r.id, (None, None))
        output.append(
            MemoryResult(
                id=r.id,
                content=r.content,
                memory_type=r.memory_type,
                tags=tags_map.get(r.id, []),
                metadata=metadata,
                created_at=str(created_at) if created_at else None,
                rrf_score=r.rrf_score,
            )
        )
    return output
