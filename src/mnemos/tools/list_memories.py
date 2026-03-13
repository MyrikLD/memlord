import math

from fastmcp import FastMCP
from mcp.types import ToolAnnotations
from mnemos.db import MCPSessionDep
from mnemos.models import Memory, MemoryTag, Tag
from mnemos.schemas import MemoryListItem, MemoryPage
from mnemos.tools.retrieve import _fetch_tags
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

mcp = FastMCP()

_COLS = (
    Memory.id,
    Memory.content,
    Memory.memory_type,
    Memory.extra_data,
    Memory.created_at,
)


@mcp.tool(
    output_schema=MemoryPage.model_json_schema(),
    annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False),
)
async def list_memories(
    page: int = 1,
    page_size: int = 10,
    memory_type: str | None = None,
    tag: str | None = None,
    s: AsyncSession = MCPSessionDep,  # type: ignore[assignment]
) -> MemoryPage:
    """Paginated list of memories with optional type/tag filters."""
    page_size = min(page_size, 100)
    offset = (page - 1) * page_size

    q = select(*_COLS)

    if memory_type:
        q = q.where(Memory.memory_type == memory_type)

    if tag:
        tag_subq = (
            select(MemoryTag.memory_id)
            .join(Tag, MemoryTag.tag_id == Tag.id)
            .where(Tag.name == tag.lower().strip())
        )
        q = q.where(Memory.id.in_(tag_subq))

    total = await s.scalar(select(func.count()).select_from(q.subquery())) or 0

    rows = (
        (
            await s.execute(
                q.order_by(Memory.created_at.desc()).limit(page_size).offset(offset)
            )
        )
        .mappings()
        .all()
    )

    total_pages = math.ceil(total / page_size) if total else 0

    if not rows:
        return MemoryPage(
            items=[],
            total=total,
            page=page,
            page_size=page_size,
            total_pages=total_pages,
        )

    ids: list[int] = [row["id"] for row in rows]
    tags_map = await _fetch_tags(s, ids)

    return MemoryPage(
        items=[
            MemoryListItem(
                id=row["id"],
                content=row["content"],
                memory_type=row["memory_type"],
                metadata=row["extra_data"],
                tags=tags_map.get(row["id"], []),
                created_at=str(row["created_at"]),
            )
            for row in rows
        ],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )
