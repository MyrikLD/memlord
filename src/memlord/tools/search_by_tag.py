from typing import Literal

from fastmcp import FastMCP
from mcp.types import ToolAnnotations
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from memlord.auth import MCPUserDep
from memlord.dao import MemoryDao
from memlord.dao.workspace import WorkspaceDao
from memlord.db import MCPSessionDep
from memlord.filters import has_tag, not_expired, tag_group_select
from memlord.models import Memory, Workspace
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
async def search_by_tag(
    tags: set[str],
    operation: Literal["AND", "OR"] = "AND",
    s: AsyncSession = MCPSessionDep,  # type: ignore[assignment]
    uid: int = MCPUserDep,  # type: ignore[assignment]
) -> MemoryPage:
    """Find memories by tag. Returns all results (no pagination).

    operation="AND" (default): memory must have ALL specified tags.
    operation="OR": memory must have AT LEAST ONE of the specified tags.
    Tags are case-insensitive and match through their aliases. Use retrieve_memory()
    for semantic/text search or list_memories(tag=...) to browse a single tag with pagination.
    """
    normalized = sorted({normalize_tag(t) for t in tags} - {""})
    if not normalized:
        return MemoryPage()

    workspace_ids = await WorkspaceDao(s, uid).get_accessible_workspace_ids()

    if operation == "AND":
        # Requested names covered by the memory's tag groups, one per name.
        group_q, requested = tag_group_select()
        matching_count = (
            group_q.with_only_columns(func.count(func.distinct(requested.name)))
            .where(requested.name.in_(normalized))
            .scalar_subquery()
        )
        tag_filter = matching_count == len(normalized)
    else:
        tag_filter = has_tag(lambda t: t.name.in_(normalized))

    stmt = (
        select(*_COLS)
        .join(Workspace, Memory.workspace_id == Workspace.id)
        .where(tag_filter, Memory.workspace_id.in_(workspace_ids), not_expired())
        .order_by(Memory.created_at.desc())
    )

    rows = (await s.execute(stmt)).mappings().all()
    if not rows:
        return MemoryPage()

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
        total=len(rows),
        page=1,
        page_size=len(rows),
    )
