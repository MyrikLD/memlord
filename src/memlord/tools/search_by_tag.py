from typing import Literal

from fastmcp import FastMCP
from mcp.types import ToolAnnotations
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from memlord.auth import UserDep
from memlord.dao import MemoryDao
from memlord.dao.workspace import WorkspaceDao
from memlord.db import MCPSessionDep
from memlord.models import Memory, MemoryTag, Tag
from memlord.schemas import MemoryListItem

mcp = FastMCP()

_COLS = (
    Memory.id,
    Memory.content,
    Memory.memory_type,
    Memory.extra_data,
    Memory.created_at,
    Memory.workspace_id,
)


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False))
async def search_by_tag(
    tags: list[str],
    operation: Literal["AND", "OR"] = "AND",
    s: AsyncSession = MCPSessionDep,  # type: ignore[assignment]
    uid: int = UserDep,  # type: ignore[assignment]
) -> list[MemoryListItem]:
    """Search memories by tags. AND: all tags present. OR: any tag present."""
    if not tags:
        return []

    normalized = [t.lower().strip() for t in tags if t.strip()]
    if not normalized:
        return []

    workspace_ids = await WorkspaceDao(s).get_accessible_workspace_ids(uid)
    access_filter = Memory.workspace_id.in_(workspace_ids)

    if operation == "AND":
        matching_count = (
            select(func.count(Tag.id.distinct()))
            .select_from(MemoryTag)
            .join(Tag, MemoryTag.tag_id == Tag.id)
            .where(MemoryTag.memory_id == Memory.id)
            .where(Tag.name.in_(normalized))
            .scalar_subquery()
        )
        stmt = (
            select(*_COLS)
            .where(matching_count == len(normalized), access_filter)
            .order_by(Memory.created_at.desc())
        )
    else:
        stmt = (
            select(*_COLS)
            .join(MemoryTag, Memory.id == MemoryTag.memory_id)
            .join(Tag, MemoryTag.tag_id == Tag.id)
            .where(Tag.name.in_(normalized), access_filter)
            .distinct()
            .order_by(Memory.created_at.desc())
        )

    rows = (await s.execute(stmt)).mappings().all()
    if not rows:
        return []

    ids: list[int] = [row["id"] for row in rows]
    tags_map = await MemoryDao(s, uid).fetch_tags(ids)

    return [
        MemoryListItem(
            id=row["id"],
            content=row["content"],
            memory_type=row["memory_type"],
            metadata=row["extra_data"],
            tags=tags_map.get(row["id"], []),
            created_at=row["created_at"],
            workspace_id=row["workspace_id"],
        )
        for row in rows
    ]
