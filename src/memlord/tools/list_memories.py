from fastmcp import FastMCP
from mcp.types import ToolAnnotations
from pydantic import Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from memlord.auth import MCPUserDep
from memlord.dao import MemoryDao
from memlord.dao.workspace import WorkspaceDao
from memlord.db import MCPSessionDep
from memlord.filters import has_tag, not_expired
from memlord.models import Memory, Workspace
from memlord.schemas import MemoryType
from memlord.schemas.tools import MemoryItem, MemoryPage
from memlord.tags import normalize_tag

mcp = FastMCP()

_COLS = (
    Memory.id,
    Memory.name,
    Memory.memory_type,
    Memory.extra_data.label("metadata"),
    Memory.created_at,
    Memory.expires_at,
    Workspace.name.label("workspace"),
)


@mcp.tool(
    output_schema=MemoryPage.model_json_schema(),
    annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False),
)
async def list_memories(
    page: int = Field(1, ge=1),
    page_size: int = Field(10, ge=1, le=100),
    memory_type: MemoryType | None = None,
    tag: str | None = Field(None, description="Single tag name; matches the tag and its aliases"),
    s: AsyncSession = MCPSessionDep,  # type: ignore[assignment]
    uid: int = MCPUserDep,  # type: ignore[assignment]
) -> MemoryPage:
    """
    Browse all memories ordered by creation date (newest first).
    Returns full content (not snippets). Use to enumerate or audit without a specific query.
    """
    offset = (page - 1) * page_size

    workspace_ids = await WorkspaceDao(s, uid).get_accessible_workspace_ids()
    q = (
        select(*_COLS)
        .join(Workspace, Memory.workspace_id == Workspace.id)
        .where(Memory.workspace_id.in_(workspace_ids), not_expired())
    )

    if memory_type:
        q = q.where(Memory.memory_type == memory_type)

    if tag:
        wanted = normalize_tag(tag)
        q = q.where(has_tag(lambda t: t.name == wanted))

    total = await s.scalar(select(func.count()).select_from(q.subquery())) or 0
    q = q.order_by(Memory.created_at.desc()).limit(page_size).offset(offset)

    rows = (await s.execute(q)).mappings().all()

    if not rows:
        return MemoryPage(
            items=[],
            total=total,
            page=page,
            page_size=page_size,
        )

    ids: list[int] = [row["id"] for row in rows]
    tags_map = await MemoryDao(s, uid).fetch_tags(ids)

    return MemoryPage(
        items=[
            MemoryItem(
                **row,
                tags=tags_map.get(row["id"], set()),
            )
            for row in rows
        ],
        total=total,
        page=page,
        page_size=page_size,
    )
