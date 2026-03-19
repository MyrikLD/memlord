from datetime import datetime, timezone

from dateparser.search import search_dates  # type: ignore[import-untyped]
from fastmcp import FastMCP
from mcp.types import ToolAnnotations
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from memlord.auth import UserDep
from memlord.dao import MemoryDao
from memlord.dao.workspace import WorkspaceDao
from memlord.db import MCPSessionDep
from memlord.models import Memory
from memlord.schemas import MemoryType, RecallResult
from memlord.search import hybrid_search

mcp = FastMCP()


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False))
async def recall_memory(
    query: str,
    n_results: int = 5,
    memory_type: MemoryType | None = None,
    s: AsyncSession = MCPSessionDep,  # type: ignore[assignment]
    uid: int = UserDep,  # type: ignore[assignment]
) -> list[RecallResult]:
    """Search memories by time expression + semantics.

    Examples: "last week", "yesterday", "about Python last month".
    """
    date_from: datetime | None = None
    date_to: datetime | None = None
    semantic_query = query

    found = search_dates(
        query,
        settings={"PREFER_DATES_FROM": "past", "RETURN_AS_TIMEZONE_AWARE": False},
    )
    if found:
        dts = [dt for _, dt in found]
        # Truncate to start of day: dateparser returns "now" time for expressions like
        # "today"/"yesterday"/"last week", making the window near-zero otherwise.
        date_from = min(dts).replace(hour=0, minute=0, second=0, microsecond=0)
        date_to = datetime.now(timezone.utc).replace(tzinfo=None)

        remaining = query
        for date_str, _ in found:
            remaining = remaining.replace(date_str, "")
        semantic_query = remaining.strip() or query

    workspace_ids = await WorkspaceDao(s).get_accessible_workspace_ids(uid)
    results = await hybrid_search(
        s,
        query=semantic_query,
        workspace_ids=workspace_ids,
        limit=n_results,
        similarity_threshold=0.0,
        date_from=date_from,
        date_to=date_to,
        memory_type=memory_type,
    )

    if not results:
        return []

    ids = [r.id for r in results]
    tags_map = await MemoryDao(s, uid).fetch_tags(ids)

    rows = await s.execute(
        select(Memory.id, Memory.created_at).where(Memory.id.in_(ids))
    )
    created_map = {row.id: row.created_at for row in rows.fetchall()}

    return [
        RecallResult(
            id=r.id,
            content=r.content,
            memory_type=r.memory_type,
            tags=tags_map.get(r.id, []),
            created_at=str(created_map.get(r.id, "")),
            workspace_id=r.workspace_id,
        )
        for r in results
    ]
