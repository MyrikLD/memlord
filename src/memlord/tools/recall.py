from datetime import datetime, timezone

from dateparser.search import search_dates  # type: ignore[import-untyped]
from fastmcp import FastMCP
from mcp.types import ToolAnnotations
from pydantic import Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from memlord.auth import MCPUserDep
from memlord.dao import MemoryDao
from memlord.dao.workspace import WorkspaceDao
from memlord.db import MCPSessionDep
from memlord.models import Memory
from memlord.schemas import MemoryType
from memlord.schemas.tools import RecallPage, RecallResult
from memlord.search import hybrid_search

mcp = FastMCP()


@mcp.tool(
    output_schema=RecallPage.model_json_schema(),
    annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False),
)
async def recall_memory(
    query: str = Field(
        ...,
        description="Query string",
        examples=["last week", "yesterday", "about Python last month"],
    ),
    n_results: int = Field(5, ge=1),
    memory_type: MemoryType | None = None,
    workspace: str | None = None,
    s: AsyncSession = MCPSessionDep,  # type: ignore[assignment]
    uid: int = MCPUserDep,  # type: ignore[assignment]
) -> RecallPage:
    """Search memories by time expression + semantics. Returns names + metadata only.

    Examples: "last week", "yesterday", "about Python last month".
    Use get_memory(name=...) to fetch full content of a specific result.
    Pass workspace=<name> to search only within a specific workspace.
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

    ws_dao = WorkspaceDao(s, uid)
    if workspace is not None:
        ws = await ws_dao.get_by_name(workspace)
        if ws is None:
            raise ValueError(f"Workspace {workspace!r} not found")
        workspace_ids = [ws.id]
    else:
        workspace_ids = await ws_dao.get_accessible_workspace_ids()
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
        return RecallPage()

    ids = [r.id for r in results]
    tags_map = await MemoryDao(s, uid).fetch_tags(ids)

    rows = await s.execute(select(Memory.id, Memory.created_at).where(Memory.id.in_(ids)))
    created_map = {row.id: row.created_at for row in rows.fetchall()}

    return RecallPage(
        items=[
            RecallResult(
                name=r.name,
                memory_type=r.memory_type,
                tags=tags_map.get(r.id, set()),
                created_at=created_map[r.id],
                workspace=r.workspace,
            )
            for r in results
        ]
    )
